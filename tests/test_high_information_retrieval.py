import copy
from dataclasses import asdict
import json
import time

import pytest
from jsonschema import Draft202012Validator

from enterprise_data_context.environment import AvailabilityState, EnvironmentBindingResult
from enterprise_data_context.indexes.page import PageIndex
from enterprise_data_context.models import ContextFragment, Evidence, SourceLocation, TypedReference
from enterprise_data_context.compiler import ContextCompiler
from enterprise_data_context.runtime import from_compiled
from enterprise_data_context.persistence import save_compiled
from enterprise_data_context.runtime import load_runtime
from enterprise_data_context.tools import DataContextTools
from explore_agent import ExploreAgent
from explore_agent.binding import build_binding_overlay
from explore_agent.bounded import SemanticLimits
from explore_agent.coverage import requirement, assess, assess_environment
from explore_agent.evaluation import EvaluationCase, evaluate, assert_golden_gate, GoldenGateError
from evaluation.retrieval_golden.fixtures import corpus, environment, FixtureSemanticProvider


def test_hybrid_recovers_cross_language_and_falls_back_if_encoder_fails():
    compiled=corpus(); index=compiled["page_index"]
    assert not index.baseline_search("signal strength")
    assert index.search("signal strength",top_k=1)[0].name=="RSRP"
    assert "vector" in index.search("signal strength",top_k=1)[0].reasons
    class BrokenEncoder:
        def encode(self, texts):
            raise TimeoutError("unavailable encoder")
    broken=PageIndex(encoder=BrokenEncoder())
    for page in compiled["pages"]:
        broken.add(page)
    assert broken.search("RSRP")[0].name=="RSRP"
    assert broken.last_warnings[0]["code"]=="vector_retrieval_unavailable"


def test_index_replacement_evicts_stale_tokens_and_candidates():
    page=next(p for p in corpus()["pages"] if p.name=="Radio Model")
    index=PageIndex(); index.add(page)
    updated=copy.deepcopy(page); updated.identity_status="CANDIDATE"
    index.add(updated)
    assert index.search("Radio Model")==[]
    assert page.path not in index.docs


def test_elements_find_deep_field_without_polluting_page_search_and_survive_reload(tmp_path):
    compiled=corpus(); page=next(p for p in compiled["pages"] if p.name=="Radio Model")
    tools=DataContextTools(from_compiled(compiled).retrieval)
    assert not compiled["page_index"].baseline_search("subscriber_key")
    result=tools.data_expand([page.path],["fields"],query="subscriber_key",top_k=1)
    row=result[page.path]["elements"][0]
    assert row["value"]=="subscriber_key" and row["evidence"]
    assert result[page.path]["fields"]==["subscriber_key"]
    other=next(p.path for p in compiled["pages"] if p.name=="Incomplete Model")
    assert tools.data_expand([other],["fields"],query="subscriber_key")[other]["elements"]==[]
    save_compiled(compiled,tmp_path)
    reloaded=DataContextTools(load_runtime(tmp_path).retrieval)
    assert reloaded.data_expand([page.path],["fields"],query="subscriber_key")[page.path]["elements"][0]["element_id"]==row["element_id"]


def test_candidate_elements_are_never_indexed():
    compiled=corpus(); page=copy.deepcopy(next(p for p in compiled["pages"] if p.name=="Radio Model"))
    page.section_status["important_fields"]="CANDIDATE"
    index=compiled["element_index"]; index.add(page)
    assert index.search("subscriber_key",[page.path])==[]
    page.identity_status="CANDIDATE"; page.section_status["important_fields"]="EXPLICIT"
    index.add(page)
    assert index.search("subscriber_key",[page.path])==[]


def test_entity_coverage_isolated_and_reference_never_satisfies_environment():
    compiled=corpus(); agent=ExploreAgent(from_compiled(compiled).retrieval)
    requirements=[requirement("data://physical-models/radio-model","fields",name="Radio Model"),
                  requirement("data://physical-models/incomplete-model","fields",name="Incomplete Model"),
                  requirement("data://physical-models/radio-model","fields","ENVIRONMENT","Radio Model")]
    bundle=agent.explore("Radio Model 与 Incomplete Model 的字段",requirements=requirements,token_budget=4000)
    assert [bundle.coverage[r["id"]]["status"] for r in requirements]==["SATISFIED","UNKNOWN","UNKNOWN"]
    assert bundle.coverage_summary["fields"] is False
    assert all(row["knowledge_layer"]=="REFERENCE" for row in bundle.primary_contexts)
    Draft202012Validator(json.load(open("contracts/context-bundle.schema.json"))).validate(asdict(bundle))


@pytest.mark.parametrize("state",[AvailabilityState.UNSUPPORTED,AvailabilityState.UNAVAILABLE,AvailabilityState.TRUNCATED,AvailabilityState.NOT_FOUND_CONFIRMED])
def test_unknown_environment_is_not_per_entity_absence(state):
    req=requirement("model-a","fields","ENVIRONMENT","Model A")
    result=EnvironmentBindingResult(required=True,state=state)
    assert assess_environment(req,result)["status"]=="UNKNOWN"
    result.requirement_coverage=[{"entity":"Model A","aspect":"fields","status":"MISSING","evidence":[{"source":"fixture"}],"complete":True,"authoritative":True}]
    assert assess_environment(req,result)["status"]=="MISSING"
    result.requirement_coverage[0]["complete"]=False
    assert assess_environment(req,result)["status"]=="UNKNOWN"


def test_conflict_and_truncated_field_dictionary_remain_partial():
    compiled=corpus(); model=next(p for p in compiled["pages"] if p.name=="Radio Model")
    model.conflicts.append({"section":"important_fields","kept":["CELL_ID"],"discarded":["OTHER"]})
    req=requirement(model.path,"fields",name=model.name)
    bundle=ExploreAgent(from_compiled(compiled).retrieval).explore("Radio Model 字段",requirements=[req])
    assert bundle.coverage[req["id"]]["status"]=="PARTIAL"
    assert bundle.conflicts
    expanded=DataContextTools(from_compiled(compiled).retrieval).data_expand([model.path],["fields"],top_k=1)
    assert expanded[model.path]["support"][0]["truncated"] is True


def test_same_name_and_cross_type_are_not_identity_bindings():
    env=environment(); env.assets[0]["attributes"]={}
    refs=[{"path":"data://physical-models/radio-model","context_type":"physical-model","name":"Radio Model"}]
    overlay=build_binding_overlay(env,refs,reference_index_version="r1",required_coverage=[])
    assert not overlay["identity_bindings"] and not overlay["derived_bindings"]
    assert overlay["candidate_bindings"][0]["assertion_status"]=="CANDIDATE"
    assert overlay["reference_only_assets"]
    env=environment(); env.assets[0]["type"]="logical-model"
    assert not build_binding_overlay(env,refs,reference_index_version="r1",required_coverage=[])["identity_bindings"]


def test_identity_mapping_and_structure_are_separate():
    env=environment(); model="data://physical-models/radio-model"
    env.assets.append({"id":"env:field","type":"field"})
    env.relations=[{"source_id":"env:radio","target_id":model,"predicate":"MAPS_TO","assertion_status":"EXPLICIT","evidence":[{"ref":"map"}]},
                   {"source_id":"env:radio","target_id":"env:field","predicate":"HAS_COLUMN","assertion_status":"EXPLICIT","evidence":[{"ref":"field"}]}]
    for relation in env.relations:
        relation["evidence"][0].update(environment_id="env-golden",snapshot_token="snapshot-v1")
    overlay=build_binding_overlay(env,[{"path":model,"context_type":"physical-model","name":"Radio Model"}],reference_index_version="r1",required_coverage=[])
    assert len(overlay["identity_bindings"])==len(overlay["semantic_mappings"])==len(overlay["structural_relations"])==1
    assert not overlay["reference_only_assets"]


def test_intent_filters_relations_and_tools_return_rich_summaries():
    ev=[Evidence(SourceLocation("fixture","fixture.json",row=1))]
    compiled=ContextCompiler().compile_fragments([
        ContextFragment("a","metric","Anchor","summary","anchor",evidence=ev,references=[TypedReference("supported_by","Useful","physical-model",evidence=ev),TypedReference("maps_to_business_object","Distractor","business-object",evidence=ev)]),
        ContextFragment("b","physical-model","Useful","summary","useful",evidence=ev),
        ContextFragment("c","business-object","Distractor","summary","distractor",evidence=ev),
    ])
    tools=DataContextTools(from_compiled(compiled).retrieval)
    search=tools.data_search("Anchor",top_k=1,intent="metric_to_models")
    assert {h["name"] for h in search["contexts"]}=={"Anchor","Useful"}
    expanded=tools.data_expand([search["contexts"][0]["path"]],["related"],intent="metric_to_models")
    relation=next(iter(expanded.values()))["related"]["outgoing"][0]
    assert relation["context"]["content"] and relation["evidence"]
    assert not {"source","target"} & relation.keys()


def test_expansion_budget_does_not_keep_proof_for_omitted_fields():
    compiled=corpus(); path="data://physical-models/radio-model"
    expanded=DataContextTools(from_compiled(compiled).retrieval).data_expand([path],["fields"],token_budget=1)[path]
    assert expanded["truncated"] and not expanded.get("fields") and not expanded.get("support")


class BadProvider:
    def complete(self, *, task, **kwargs):
        if task=="route":
            return {"intent":"raw_graph_traversal","entities":["invented"],"aspects":[]}
        return {"observations":[{"evidence_id":"fake","excerpt":"this reference is deployed"}]}


def test_bounded_semantic_outputs_reject_invented_route_and_facts():
    bundle=ExploreAgent(from_compiled(corpus()).retrieval,semantic_provider=BadProvider()).explore("RSRP",top_k=1)
    assert bundle.query["interpreted_intent"]=="generic"
    assert not bundle.reasoning_observations
    assert [row["status"] for row in bundle.telemetry["semantic_calls"]]==["REJECTED","REJECTED"]
    assert bundle.telemetry["tool_calls"]==2
    assert "deployed" not in bundle.summary


def test_semantic_timeout_and_input_output_limits_fall_back():
    class Slow:
        def complete(self, **kwargs):
            time.sleep(.1)
            return {}
    started=time.monotonic()
    bundle=ExploreAgent(from_compiled(corpus()).retrieval,semantic_provider=Slow(),semantic_limits=SemanticLimits(timeout_seconds=.01)).explore("RSRP",top_k=1)
    assert time.monotonic()-started<.2
    assert all(row["status"]=="TIMEOUT" for row in bundle.telemetry["semantic_calls"])
    time.sleep(.1)  # let bounded worker slots return before the next fixture
    bundle=ExploreAgent(from_compiled(corpus()).retrieval,semantic_provider=BadProvider(),semantic_limits=SemanticLimits(max_input_tokens=1)).explore("RSRP")
    assert all(row["status"]=="INPUT_LIMIT" and not row["calls"] for row in bundle.telemetry["semantic_calls"])


def test_valid_joint_reasoner_observations_preserve_evidence_layer():
    bundle=ExploreAgent(from_compiled(corpus()).retrieval,semantic_provider=FixtureSemanticProvider()).explore("RSRP",top_k=1)
    assert bundle.reasoning_observations
    assert all(row["knowledge_layer"]=="REFERENCE" and row["evidence"] for row in bundle.reasoning_observations)
    assert all(row["status"]=="ACCEPTED" for row in bundle.telemetry["semantic_calls"])
    assert sum(row["provider_tokens"] for row in bundle.telemetry["semantic_calls"])==180


def test_resume_rejects_new_query_and_requirements():
    agent=ExploreAgent(from_compiled(corpus()).retrieval)
    first=agent.explore("RSRP")
    with pytest.raises(ValueError,match="query/requirements"):
        agent.explore("Latency",state=first.exploration_state)


def test_golden_gate_detects_false_positives_and_missing_measurements():
    agent=ExploreAgent(from_compiled(corpus()).retrieval)
    report=evaluate(agent,[EvaluationCase("precision","RSRP",expected_contexts=["RSRP"],relevant_contexts=["RSRP"],explore_options={"top_k":1})])
    assert report.bundle_precision==.5 and report.passed==0
    with pytest.raises(GoldenGateError):
        assert_golden_gate(report)
    report=evaluate(agent,[EvaluationCase("unscored","RSRP")])
    assert report.binding_precision is None
    with pytest.raises(GoldenGateError,match="unscored"):
        assert_golden_gate(report,minimums={"binding_precision":1})


def test_missing_specific_field_is_not_satisfied_by_other_fields():
    req=requirement("data://physical-models/radio-model","fields",name="Radio Model",selector="NONEXISTENT_COLUMN")
    bundle=ExploreAgent(from_compiled(corpus()).retrieval).explore("Radio Model 字段",requirements=[req])
    assert bundle.coverage[req["id"]]["status"]=="UNKNOWN"
    req=requirement("data://physical-models/radio-model","fields",name="Radio Model",selector="subscriber_key")
    bundle=ExploreAgent(from_compiled(corpus()).retrieval).explore("Radio Model 字段",requirements=[req])
    assert bundle.coverage[req["id"]]["status"]=="SATISFIED"


def test_underscore_identifier_does_not_become_a_topic_scope():
    from explore_agent.router import QueryRouter
    assert QueryRouter().route("Radio Model 的 subscriber_key 字段")=={}


def test_unretrieved_second_metric_keeps_its_requirement_unknown():
    bundle=ExploreAgent(from_compiled(corpus()).retrieval).explore("RSRP 和 RSRQ 有哪些模型提供？",top_k=1)
    rows=[row for row in bundle.coverage.values() if row["entity_name"]=="RSRQ" and row["layer"]=="REFERENCE"]
    assert rows and all(row["status"]=="UNKNOWN" for row in rows)


def test_ambiguous_crosswalk_and_stale_evidence_do_not_confirm_identity():
    model="data://physical-models/radio-model"
    refs=[{"path":model,"context_type":"physical-model","name":"Radio Model"}]
    env=environment(); env.assets.append({**copy.deepcopy(env.assets[0]),"id":"env:duplicate"})
    overlay=build_binding_overlay(env,refs,reference_index_version="r1",required_coverage=[])
    assert not overlay["identity_bindings"]
    assert any(r["rule"]=="ambiguous_provider_crosswalk/v2" for r in overlay["candidate_bindings"])
    env=environment(); env.assets[0]["evidence"][0]["snapshot_token"]="stale"
    assert not build_binding_overlay(env,refs,reference_index_version="r1",required_coverage=[])["identity_bindings"]


def test_semantic_router_cannot_remove_environment_gate_or_explicit_intent():
    class Downgrade:
        def complete(self, *,task,**kwargs):
            return {"intent":"generic","entities":[],"aspects":[]} if task=="route" else {"observations":[]}
    bundle=ExploreAgent(from_compiled(corpus()).retrieval,semantic_provider=Downgrade()).explore("RSRP 有哪些模型提供？")
    assert bundle.environment["binding_required"]
    assert bundle.query["interpreted_intent"]=="metric_to_models"
    assert bundle.telemetry["semantic_calls"][0]["status"]=="REJECTED"


def test_two_hop_requirement_assembly_is_one_batched_tool_expansion():
    compiled=corpus()
    ev=[Evidence(SourceLocation("purpose","purpose.json",row=1))]
    fragments=compiled["fragments"]+[ContextFragment("purpose","analysis-purpose","Coverage Research","summary","覆盖分析",evidence=ev,
        references=[TypedReference("uses_metric","RSRP","metric",evidence=ev)])]
    compiled=ContextCompiler().compile_fragments(fragments)
    req=requirement("data://purposes/coverage-research","models",name="Coverage Research")
    bundle=ExploreAgent(from_compiled(compiled).retrieval).explore("Coverage Research 需要哪些数据？",top_k=1,requirements=[req],token_budget=5000)
    assert {h["name"] for h in bundle.primary_contexts}=={"Coverage Research","RSRP","Radio Model"}
    assert bundle.coverage[req["id"]]["status"]=="SATISFIED"
    assert bundle.telemetry["tool_calls"]==2
    assert bundle.coverage[req["id"]]["evidence"][0]["composition_rule"]=="uses_metric_supported_by/v1"


def test_required_contract_and_complete_golden_metrics():
    from evaluation.scripts.run_retrieval_golden import run
    from evaluation.retrieval_golden.fixtures import cases
    schema=json.load(open("contracts/coverage-requirements.schema.json"))
    Draft202012Validator.check_schema(schema)
    for case in cases():
        if case.explore_options.get("requirements"):
            Draft202012Validator(schema).validate(case.explore_options["requirements"])
    reports=run()
    report=reports["hybrid"]
    assert report.total==report.passed
    assert report.anchor_recall>reports["lexical_ablation"].anchor_recall
    assert_golden_gate(report,minimums={"anchor_recall":1,"bundle_recall":1,"bundle_precision":1,"binding_precision":1,"focused_expansion_success":1},maximums={"tool_calls":3,"token_cost":10000})
    assert all(count>0 for count in report.metric_sample_counts.values())


def test_semantic_route_cannot_add_environment_calls_for_a_bare_metric():
    class Overroute:
        def complete(self, *,task,**kwargs):
            return {"intent":"model_understanding","entities":["RSRP"],"aspects":[]} if task=="route" else {"observations":[]}
    bundle=ExploreAgent(from_compiled(corpus()).retrieval,semantic_provider=Overroute()).explore("RSRP")
    assert bundle.telemetry["total_tool_calls"]==2
    assert not bundle.environment["binding_required"]
    assert bundle.telemetry["semantic_calls"][0]["status"]=="REJECTED"


def test_coverage_evaluation_preserves_distinct_selectors():
    requirements=[requirement("data://physical-models/radio-model","fields",name="Radio Model",selector=s) for s in ("subscriber_key","MISSING_COLUMN")]
    case=EvaluationCase("selectors","Radio Model 字段",expected_coverage={requirements[0]["id"]:"SATISFIED",requirements[1]["id"]:"UNKNOWN"},explore_options={"requirements":requirements})
    report=evaluate(ExploreAgent(from_compiled(corpus()).retrieval),[case])
    assert report.passed==1 and report.coverage_accuracy==1
    from evaluation.retrieval_golden.fixtures import cases
    schema=json.load(open("evaluation/contracts/retrieval-evaluation-case.schema.json"))
    Draft202012Validator.check_schema(schema)
    for fixture in [case,*cases()]:
        Draft202012Validator(schema).validate(asdict(fixture))
