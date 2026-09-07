import copy
import json
from dataclasses import asdict

import pytest
from jsonschema import Draft202012Validator

from enterprise_data_context.indexes.page import PageIndex
from enterprise_data_context.indexes.dense import DisabledDenseEncoder
from enterprise_data_context.runtime import from_compiled
from enterprise_data_context.tools import DataContextTools
from explore_agent import ExploreAgent
from explore_agent.binding import build_binding_overlay
from explore_agent.coverage import CoverageRequirement, assess, requirement, validate_requirements, missing_requirements
from explore_agent.evaluation import EvaluationCase, evaluate, assert_golden_gate, GoldenGateError
from evaluation.retrieval_golden.correctness import corpus, cases, MODEL, POLICY, CorrectnessEnvironment
from evaluation.retrieval_golden.fixtures import environment


def agent():
    return ExploreAgent(from_compiled(corpus()).retrieval,environment_adapter=CorrectnessEnvironment())


@pytest.mark.parametrize("case",[c for c in cases() if c.case_id not in {"cross-language-semantic"}],ids=lambda c:c.case_id)
def test_correctness_oracles_without_semantic_provider(case):
    report=evaluate(agent(),[case])
    assert report.passed==1, report.cases


def test_golden_cases_and_typed_bindings_validate_contracts():
    case_schema=json.load(open("evaluation/contracts/retrieval-evaluation-case.schema.json"))
    binding_schema=json.load(open("contracts/binding-overlay.schema.json"))
    requirements_schema=json.load(open("contracts/coverage-requirements.schema.json"))
    for case in cases():
        Draft202012Validator(case_schema).validate(asdict(case))
        if case.explore_options.get("requirements"):
            Draft202012Validator(requirements_schema).validate(case.explore_options["requirements"])
        if case.expected_bindings is not None:
            bundle=agent().explore(case.query,**case.explore_options)
            Draft202012Validator(binding_schema).validate(bundle.binding_overlay)


def test_five_states_are_evidence_linked_and_not_applicable_is_resolved():
    requirements=[requirement(POLICY,"formula",name="Stored Counter"),requirement(POLICY,"constraints",name="Stored Counter"),
                  requirement(POLICY,"fields",name="Stored Counter")]
    bundle=agent().explore("Stored Counter",requirements=requirements,top_k=1)
    assert [r["status"] for r in bundle.coverage.values()]==["NOT_APPLICABLE","MISSING","UNKNOWN"]
    for row in bundle.coverage.values():
        assert row["context_refs"]==[POLICY]
        assert bool(row["evidence"]) == (row["status"]!="UNKNOWN")
    assert requirements[0]["id"] not in missing_requirements(bundle.coverage)
    schema=json.load(open("contracts/context-bundle.schema.json"))
    Draft202012Validator(schema).validate(asdict(bundle))
    typed=CoverageRequirement("r",MODEL,"fields",selector="subscriber_key")
    assert validate_requirements([typed])[0]["entity_name"]==MODEL


@pytest.mark.parametrize("status,complete,authoritative,expected",[
    ("MISSING",False,True,"UNKNOWN"),("MISSING",True,False,"UNKNOWN"),
    ("NOT_APPLICABLE",False,False,"UNKNOWN"),("NOT_APPLICABLE",False,True,"NOT_APPLICABLE")])
def test_declarations_need_positive_scoped_proof(status,complete,authoritative,expected):
    req=requirement(MODEL,"fields",name="Typed Catalog")
    proof={"aspect":"fields","path":MODEL,"section":"important_fields","status":"EXPLICIT",
           "evidence":[{"source_id":"test"}],"coverage_status":status,"complete":complete,
           "authoritative":authoritative,"declaration_reason":"Documented applicability/inventory"}
    hit={"path":MODEL,"name":"Typed Catalog","support":[proof]}
    row=assess([req],[hit],{},environment())[req["id"]]
    assert row["status"]==expected
    proof["evidence"]=[]
    assert assess([req],[hit],{},environment())[req["id"]]["status"]=="UNKNOWN"


def test_ambiguous_context_names_cannot_jointly_satisfy_entity():
    req=requirement("unresolved","fields",name="Repeated")
    hits=[{"path":p,"name":"Repeated","support":[{"path":p,"aspect":"fields","status":"EXPLICIT","evidence":[{"source":"test"}]}]}
          for p in ("data://a","data://b")]
    assert assess([req],hits,{},environment())[req["id"]]["status"]=="PARTIAL"


def test_index_queries_all_five_kinds_with_parent_pages_and_no_candidate_leak():
    c=corpus(); index=c["element_index"]
    for query,kind in [("subscriber_key","Field"),("customer_age","Attribute"),("COUNT(subscriber_key)","Formula"),
                       ("C_RADIO_001","Counter"),("customer_id","JoinKey")]:
        row=next(r for r in index.search(query) if r["kind"]==kind)
        assert row["parent_context"]["path"]==MODEL and row["parent_context"]["content"]
        assert row["match"]=="EXACT_IDENTIFIER"
    assert not index.search("unapproved_field")
    assert "unapproved_field" not in json.dumps(index.expand(MODEL,["fields"]))
    assert not index.search("subscriber_key",[MODEL],["hierarchy","related"])
    assert not index.search("description",[MODEL])  # JSON property names aren't content.


def test_focused_oracle_does_not_accept_another_parent_or_description():
    case=next(c for c in cases() if c.case_id=="typed-Field")
    case.expected_elements=[{"parent_path":"data://wrong","kind":"Field","identifier":"subscriber_key"}]
    report=evaluate(agent(),[case])
    assert report.focused_expansion_success==0 and report.passed==0
    with pytest.raises(GoldenGateError):
        assert_golden_gate(report)


@pytest.mark.parametrize("key",["stable_id","strong_key"])
def test_same_type_scoped_strong_identity_and_ambiguity(key):
    env=environment(); env.assets[0]["attributes"]={"identity_namespace":"catalog-v1",key:"tenant.schema.table"}
    ref={"path":MODEL,"context_type":"physical-model","name":"Different display name",
         "binding_identity":{"keys":{"identity_namespace":"catalog-v1","environment_id":"env-golden",key:"tenant.schema.table"},
                             "status":"EXPLICIT","evidence":[{"source_id":"approved-crosswalk"}]}}
    def overlay():
        return build_binding_overlay(env,[ref],reference_index_version="ref-v1",required_coverage=[])
    assert len(overlay()["identity_bindings"])==1
    ref["context_type"]="logical-model"
    assert not overlay()["identity_bindings"]
    ref["context_type"]="physical-model"
    ref["binding_identity"]["keys"]["identity_namespace"]="different"
    assert not overlay()["identity_bindings"]
    ref["binding_identity"]["keys"]["identity_namespace"]="catalog-v1"
    env.assets.append({**copy.deepcopy(env.assets[0]),"id":"duplicate"})
    assert not overlay()["identity_bindings"]


def test_stale_relation_and_mixed_snapshot_identity_are_rejected():
    env=environment(); ref={"path":"data://physical-models/radio-model","context_type":"physical-model","name":"Radio Model"}
    env.assets[0]["evidence"].append({"environment_id":"env-golden","snapshot_token":"stale"})
    env.relations=[{"source_id":"env:radio","target_id":ref["path"],"predicate":"MAPS_TO","assertion_status":"EXPLICIT",
                    "evidence":[{"environment_id":"env-golden","snapshot_token":"stale"}]}]
    overlay=build_binding_overlay(env,[ref],reference_index_version="ref-v1",required_coverage=[])
    assert not overlay["identity_bindings"] and not overlay["semantic_mappings"]
    assert overlay["reference_only_assets"]


def test_same_name_field_and_business_attribute_cannot_be_identity():
    env=environment()
    env.assets[0].update(type="field",name="subscriber_id",attributes={"reference_path":"data://attributes/subscriber-id"})
    ref={"path":"data://attributes/subscriber-id","context_type":"business-attribute","name":"subscriber_id"}
    overlay=build_binding_overlay(env,[ref],reference_index_version="ref-v1",required_coverage=[])
    assert not overlay["identity_bindings"]
    assert overlay["candidate_bindings"][0]["binding_kind"]=="SEMANTIC_MAPPING"
    assert overlay["reference_only_assets"]


def test_dense_channel_uses_query_encoding_and_versioned_cache_and_fails_closed():
    class DenseFixture:
        channel="dense"
        version="fixture/1"
        calls=0
        def encode(self,texts):
            self.calls+=1
            return [[1.,0.] if "Stored Counter" in t else [0.,1.] for t in texts]
        def encode_query(self,query):
            return [1.,0.]
    encoder=DenseFixture(); index=PageIndex(encoder=encoder)
    for page in corpus()["pages"]:
        index.add(page)
    assert index.search("semantically equivalent description",top_k=1)[0].name=="Stored Counter"
    assert "dense" in index.search("semantically equivalent description",top_k=1)[0].reasons
    assert encoder.calls==1
    encoder.version="fixture/2"
    index.search("Stored Counter")
    assert encoder.calls==2
    index.encoder=DisabledDenseEncoder()
    assert index.search("Stored Counter")[0].name=="Stored Counter"
    assert index.last_warnings


def test_dense_invalid_vectors_never_escape_to_scores():
    class Invalid:
        def encode(self,texts):
            return [[float("nan")]]*len(texts)
    index=PageIndex(encoder=Invalid())
    for page in corpus()["pages"]:
        index.add(page)
    assert index.search("Stored Counter")[0].name=="Stored Counter"
    assert index.last_warnings


def test_explicit_symbol_cannot_be_replaced_by_a_semantically_similar_page():
    class AlwaysSimilar:
        def encode(self,texts):
            return [[1.,1.]]*len(texts)
    index=PageIndex(encoder=AlwaysSimilar())
    for page in corpus()["pages"]:
        index.add(page)
    assert not index.search("UNKNOWN_METRIC 有哪些模型",scope={"symbol":"UNKNOWN_METRIC"})
    assert not index.search("FORBIDDEN_ASSET_Z9")
