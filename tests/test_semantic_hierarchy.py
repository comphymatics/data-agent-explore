from copy import deepcopy
from dataclasses import asdict
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from enterprise_data_context.compiler import ContextCompiler
from enterprise_data_context.hierarchy_contracts import HierarchyEdge
from enterprise_data_context.indexes.hierarchy import HierarchyIndex, view_path
from enterprise_data_context.persistence import save_compiled, load_compiled, QualityGateError
from enterprise_data_context.runtime import from_compiled
from enterprise_data_context.tools import DataContextTools
from explore_agent import ExploreAgent
from evaluation.hierarchy.sample import sample_fragments, sample_config


def compiled(config=None):
    return ContextCompiler(hierarchy_config=config or sample_config()).compile_fragments(sample_fragments())


def named(c, name):
    return next(x for x in c["contexts"] if x.name == name)


def test_multiview_sparse_and_fact_graph_boundary():
    c = compiled(); index = c["hierarchy"]; model = named(c, "LTE_PERIODIC_MR")
    assert index.classification(model.path)["status"] == "classified"
    assert len([x for x in c["contexts"] if x.name == model.name]) == 1
    assert set(e["hierarchy_id"] for e in index.parents[model.path]) == {"analysis", "domain", "asset"}
    assert all(e["relation"] == "organized_under" for e in index.edges)
    assert not any(r.relation == "organized_under" for x in c["contexts"] for r in x.references)
    assert not [x for x in index.validate() if x["severity"] == "error"]
    logical = deepcopy(named(c, "LTE MR Logical Model"))
    logical.sections.pop("topic"); logical.sections.pop("primary_objects")
    logical.references = []
    sparse = HierarchyIndex().project([logical])
    assert sparse.parents[logical.path]
    assert any(e["parent_id"] == view_path("domain", "topic-domain", "性能") for e in sparse.parents[logical.path])
    assert not any("UNKNOWN" in n["name"] for n in sparse.nodes.values())


def test_edge_schema_precedence_keeps_audit_and_candidate_cannot_navigate():
    c = compiled(); index = c["hierarchy"]; model = named(c, "LTE_PERIODIC_MR")
    base = next(e for e in index.parents[model.path] if e["hierarchy_id"] == "domain" and e["status"] == "CONFIRMED")
    kind = index.nodes[base["parent_id"]]["kind"]
    for status, name in [("DERIVED", "rule-label"), ("CANDIDATE", "weak-label")]:
        proof = base["evidence"]
        provenance = {"method": "domain_rule", "rule_id": "test-rule", "input_facts": [{"context": model.path, "section": "topic"}]} if status == "DERIVED" else {
            "method": "llm_inference", "inference": {"candidate_set": [name], "selected": name, "confidence": .9,
                "supporting_features": {"topic": ["无线覆盖"]}, "supporting_context_ids": [model.path], "model": "fixture", "prompt_version": "test/v1"}}
        index._add_placement(model, "domain", kind, name, status, .9, proof, provenance)
    index._reindex()
    edges = [e for e in index.parents[model.path] if index.nodes[e["parent_id"]]["kind"] == kind and e["hierarchy_id"] == "domain"]
    assert {e["status"] for e in edges} == {"CONFIRMED", "DERIVED", "CANDIDATE"}
    assert all(not e["active"] for e in edges if e["status"] != "CONFIRMED")
    assert index.conflicts
    assert not index.descendants(view_path("domain", kind, "weak-label"))
    schema = json.loads(Path("contracts/semantic-hierarchy-edge.schema.json").read_text())
    for e in index.edges:
        Draft202012Validator(schema).validate(e)


def test_rule_is_organization_only_and_incremental_aggregate_rebuild():
    c = compiled(); index = c["hierarchy"]; model = named(c, "LTE_MR_NEW")
    assert "topic" not in model.sections
    assert any(e["status"] == "DERIVED" and e["provenance"].get("rule_id") == "synthetic-lte-rsrp/v1" for e in index.parents[model.path])
    billing = view_path("domain", "topic", "账单")
    untouched = index.aggregate_pages[billing]
    before = deepcopy(index.aggregate_pages[view_path("domain", "topic", "无线覆盖")])
    contexts = deepcopy(c["contexts"])
    next(x for x in contexts if x.path == model.path).sections["metrics"].append("RSRQ")
    index.update(contexts)
    after = index.aggregate_pages[view_path("domain", "topic", "无线覆盖")]
    assert before != after
    assert "RSRQ" in after["L0"]
    assert index.aggregate_pages[billing] is untouched
    assert billing not in index.last_update["rebuilt_aggregates"]
    assert index.last_update["inference_calls"] == 0
    index.update(contexts)
    assert index.last_update["rebuilt_entities"] == []
    assert index.last_update["rebuilt_aggregates"] == []


class Provider:
    def __init__(self, result):
        self.result = result; self.calls = 0
    def infer(self, *, system_prompt, payload):
        self.calls += 1
        return {"supporting_context_ids": [payload["model"]["path"]], "reasons": ["fixture selection"], **self.result}


@pytest.mark.parametrize("result,expected", [
    ({"selected": "invented", "confidence": .99}, "REJECTED"),
    ({"selected": "coverage", "confidence": .3}, "UNKNOWN"),
    ({"selected": "coverage", "confidence": .9, "supporting_context_ids": ["missing"]}, "REJECTED"),
    ({"selected": "coverage", "confidence": .9}, "CANDIDATE"),
])
def test_bounded_llm_gate(result, expected):
    config = sample_config(); config.update(llm_enabled=True, llm_model="fixture/llm", rules=[], ambiguity_margin=1)
    provider = Provider(result)
    c = ContextCompiler(hierarchy_config=config, hierarchy_provider=provider).compile_fragments(sample_fragments())
    index = c["hierarchy"]; unknown = named(c, "UNKNOWN_MODEL")
    assert provider.calls > 0
    assert "topic" not in unknown.sections
    decisions = index.inference_audit[unknown.path]["decisions"]
    assert decisions[-1]["result"] == expected
    assert not any(e["active"] and e["hierarchy_id"] == "domain" for e in index.parents[unknown.path])
    if expected == "CANDIDATE":
        edge = next(e for e in index.parents[unknown.path] if e["status"] == "CANDIDATE")
        assert edge["provenance"]["inference"]["model"] == "fixture/llm"
    else:
        assert not any(e["status"] == "CANDIDATE" for e in index.parents[unknown.path])


def test_unknown_and_no_evidence_prevent_forced_classification():
    c = compiled(); unknown = deepcopy(named(c, "UNKNOWN_MODEL"))
    unknown.sections = {}; unknown.evidence = {}
    provider = Provider({"selected": "coverage", "confidence": .99})
    config = sample_config(); config.update(llm_enabled=True, llm_model="fixture/llm")
    index = HierarchyIndex(config, provider).project([unknown])
    assert index.classification(unknown.path)["status"] == "unclassified"
    assert provider.calls == 0
    assert not index.edges


@pytest.mark.parametrize("query,mode,view", [
    ("RSRP有哪些现有模型可以提供？", "direct", None),
    ("CELL_ID在哪些表？", "direct", None),
    ("地铁弱覆盖需要哪些数据？", "hierarchical", "analysis"),
    ("有哪些数据可以描述小区无线覆盖质量？", "hierarchical", "analysis"),
    ("LTE_PERIODIC_MR属于哪个主题域和主题？", "direct", None),
    ("RSRP用于弱覆盖时还需要哪些数据？", "hybrid", "analysis"),
])
def test_runtime_routing_coverage_and_four_tool_boundary(query, mode, view):
    c = compiled(); agent = ExploreAgent(from_compiled(c).retrieval)
    bundle = agent.explore(query)
    assert bundle.retrieval_trace["mode"] == mode
    assert bundle.retrieval_trace["hierarchy_view"] == view
    assert bundle.telemetry["tool_calls"] <= 2
    assert {r["tool"] for r in bundle.telemetry["tool_trace"]} <= DataContextTools.ALLOWED
    if mode in {"hierarchical", "hybrid"}:
        assert bundle.retrieval_trace["selected_branches"]
        assert named(c, "LTE_PERIODIC_MR").path in bundle.selected_context_ids
    assert bundle.focused_expansion
    schema = json.loads(Path("contracts/context-bundle.schema.json").read_text())
    Draft202012Validator(schema).validate(asdict(bundle))


def test_aggregate_disclosure_no_environment_availability_claim():
    c = compiled(); service = from_compiled(c).retrieval
    path = view_path("domain", "topic", "无线覆盖")
    for level in ("L0", "L1", "L2"):
        read = service.data_read(path, level)
        assert read["level"] == level
    l1 = service.data_read(path)["content"]["domain"]
    assert l1["environment_availability"]["status"] == "UNRESOLVED"
    assert l1["placement_counts"]["DERIVED"]
    assert "candidate_placements" not in l1
    l2 = service.data_read(path, "L2", ["members"])["content"]["domain"]
    assert set(l2) == {"members"}
    assert set(l2["members"]) <= {x.path for x in c["contexts"]}
    assert service.data_source(path)
    result = service.data_search("地铁弱覆盖需要哪些数据？", token_budget=100)
    assert result["budget"]["estimated_tokens"] <= 100


def test_field_scale_stays_elements_and_direct_call_count_unchanged():
    fragments = sample_fragments()
    field_fragment = next(f for f in fragments if f.candidate_name == "LTE_PERIODIC_MR" and f.section_type == "important_fields")
    field_fragment.payload.extend({"name": f"EXTRA_{i}"} for i in range(10000))
    c = ContextCompiler(hierarchy_config=sample_config()).compile_fragments(fragments)
    assert len(c["pages"]) == len(c["contexts"]) == 10
    assert len(c["hierarchy"].nodes) < 30
    assert len(c["element_index"].records) >= 10000
    service = from_compiled(c).retrieval
    assert named(c, "LTE_PERIODIC_MR").path in service.data_search("EXTRA_9999在哪些表？")["selected_context_ids"]
    agent = ExploreAgent(service)
    assert agent.explore("RSRP有哪些模型？").telemetry["tool_calls"] == agent.explore("RSRP有哪些模型？", mode="direct").telemetry["tool_calls"]


def test_snapshot_overlay_roundtrip_and_publish_gate(tmp_path):
    c = compiled(); original = deepcopy(c["hierarchy"].to_dict())
    save_compiled(c, tmp_path)
    reloaded = load_compiled(tmp_path)
    assert reloaded["hierarchy"].to_dict() == original
    assert reloaded["hierarchy"].aggregate_pages == c["hierarchy"].aggregate_pages
    config = sample_config(); config["inference_enabled"] = False
    other = compiled(config)
    assert from_compiled(other).retrieval.index_version != from_compiled(compiled()).retrieval.index_version
    assert save_compiled(other, tmp_path)["index_version"] != c["index_version"]
    c["hierarchy"].edges[0]["confidence"] = 2
    with pytest.raises(QualityGateError, match="confidence"):
        save_compiled(c, tmp_path)


def test_quality_gate_cycles_duplicates_broken_members_and_candidate_promotion():
    c = compiled(); index = c["hierarchy"]
    edge = deepcopy(index.edges[0]); edge["parent_id"] = "absent"; edge["confidence"] = -1
    index.edges.append(edge)
    codes = {i["code"] for i in index.validate()}
    assert {"broken_parent_reference", "duplicate_edge", "confidence_out_of_range"} <= codes
    index = compiled()["hierarchy"]
    edge = deepcopy(next(e for e in index.edges if not index.nodes[e["child_id"]]["virtual"]))
    edge.update(parent_id=edge["child_id"], child_id=edge["parent_id"], edge_id="cycle")
    index.edges.append(edge)
    assert "hierarchy_cycle" in {i["code"] for i in index.validate()}
    index.edges[-1]["provenance"]["method"] = "llm_inference"
    index.edges[-1]["status"] = "CONFIRMED"
    assert "candidate_promoted_without_policy" in {i["code"] for i in index.validate()}
    page = next(iter(index.aggregate_pages.values()))
    next(iter(page["views"].values()))["L2"]["members"].append("invented")
    assert "aggregate_member_mismatch" in {i["code"] for i in index.validate()}


def test_explicit_tags_and_configured_tag_rule_without_canonical_mutation():
    c = compiled(); context = deepcopy(named(c, "UNKNOWN_MODEL"))
    context.sections["tags"] = [{"hierarchy_id": "domain", "kind": "topic", "label": "Explicit topic"}, "enterprise-scenario"]
    context.evidence["tags"] = context.evidence["identity"]
    config = {"version": "tags/v1", "tag_mappings": [{"tag": "enterprise-scenario", "view": "analysis", "kind": "scenario", "label": "Configured scenario", "rule_id": "approved-enterprise-rule/v1"}]}
    index = HierarchyIndex(config).project([context])
    assert {e["status"] for e in index.parents[context.path] if e["provenance"]["source_relation"] == "tags"} == {"CONFIRMED", "DERIVED"}
    assert "topic" not in context.sections


def test_incremental_deletion_and_overlay_history_survive_restart():
    c = compiled(); index = c["hierarchy"]; model = named(c, "LTE_MR_NEW")
    index.update([x for x in c["contexts"] if x.path != model.path])
    assert all(e["child_id"] != model.path for e in index.edges)
    assert all(model.path not in v["L2"]["members"] for a in index.aggregate_pages.values() for v in a["views"].values())
    assert any(h["context"] == model.path for h in index.history)
    restored = HierarchyIndex.from_dict(index.to_dict(), index.contexts.values())
    restored.update(restored.contexts.values())
    assert restored.last_update["rebuilt_entities"] == []
    assert restored.last_update["rebuilt_aggregates"] == []
    assert restored.history == index.history


def test_organization_snapshot_schema_and_config_rejection():
    from enterprise_data_context.hierarchy_config import validate_hierarchy_config
    schema = json.loads(Path("contracts/semantic-organization.schema.json").read_text())
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(compiled()["hierarchy"].to_dict())
    for bad in ({"version": "v1", "confidence_threshold": 2}, {"version": "v1", "branch_k": 0},
                {"version": "v1", "feature_weights": {"tags": -1}}):
        with pytest.raises(ValueError):
            validate_hierarchy_config(bad)
    config = sample_config(); config["taxonomy"][1]["aliases"] = ["无线覆盖"]
    with pytest.raises(ValueError, match="alias collision"):
        validate_hierarchy_config(config)


def test_derived_navigation_filter_includes_rule_member_but_never_candidate():
    c = compiled(); service = from_compiled(c).retrieval
    result = service.data_search("无线覆盖", mode="hierarchical", hierarchy="domain", scope={"topic": "无线覆盖"})
    assert named(c, "LTE_MR_NEW").path in result["selected_context_ids"]
    assert "topic" not in named(c, "LTE_MR_NEW").sections
    config = sample_config(); config["rules"] = []
    other = compiled(config); service = from_compiled(other).retrieval
    result = service.data_search("无线覆盖", mode="hierarchical", hierarchy="domain", scope={"topic": "无线覆盖"})
    assert named(other, "LTE_MR_NEW").path not in result["selected_context_ids"]


def test_aggregate_binding_only_uses_verified_identity_and_does_not_write_snapshot():
    from explore_agent.binding import aggregate_availability
    c = compiled(); service = from_compiled(c).retrieval
    trace = service.data_search("地铁弱覆盖需要哪些数据？", token_budget=20000)["retrieval_trace"]
    before = deepcopy(trace)
    model = named(c, "LTE_PERIODIC_MR")
    overlay = {"identity_bindings": [{"reference_path": model.path, "environment_asset_id": "fixture-model"}]}
    projected = aggregate_availability(trace, overlay)
    assert trace == before
    summaries = [content["environment_availability"] for page in projected["hierarchy_contexts"] for content in page["content"].values()]
    assert any(s["counts"]["available_verified"] == 1 for s in summaries)
    assert all(s["complete"] is False for s in summaries)
    assert all(v["L1"]["environment_availability"]["status"] == "UNRESOLVED" for a in c["hierarchy"].aggregate_pages.values() for v in a["views"].values())


def test_ablation_is_independent_and_keeps_unknowns_and_zero_denominators():
    from evaluation.hierarchy.run import run_sample
    result = run_sample()
    assert result["evidence_scope"] == "SYNTHETIC_ONLY"
    assert not result["headline_benchmark"]
    assert len(result["variants"]) == 5
    for variant in result["variants"].values():
        assert variant["summary"]["query_llm_tokens"] == 0
        assert variant["summary"]["tool_calls"] <= 2
        assert variant["diagnostics"]["hierarchy_candidate_precision"] is None
        assert all(row["unknown_topic_remains_unclassified"] for row in variant["cases"])


def test_incremental_new_canonical_label_replaces_virtual_group():
    c = compiled(); index = c["hierarchy"]
    topic = deepcopy(named(c, "RSRP"))
    topic.canonical_id = "topic:wireless-coverage"
    topic.context_type = "topic"; topic.name = "无线覆盖"; topic.aliases = []
    topic.path = "data://topics/wireless-coverage"
    topic.sections = {"summary": "无线覆盖"}; topic.references = []
    index.update([*c["contexts"], topic])
    model = named(c, "LTE_PERIODIC_MR")
    assert any(e["parent_id"] == topic.path for e in index.parents[model.path])
    assert view_path("domain", "topic", "无线覆盖") not in index.nodes
    assert topic.path not in index.aggregate_pages
    assert index.aggregate_pages["data://views/domain/topic/wireless-coverage"]["canonical_ref"] == topic.path
    assert not [i for i in index.validate() if i["severity"] == "error"]


def test_ancestor_navigation_does_not_override_explicit_canonical_facet():
    from enterprise_data_context.hierarchical_retrieval import organization_allowed_page
    c = compiled(); index = c["hierarchy"]; billing = named(c, "BILLING_EVENTS")
    logical = named(c, "LTE MR Logical Model")
    index._record(billing.path, "domain", logical.path, billing.path, "CONFIRMED",
                  [asdict(e) for e in billing.evidence["identity"]], source_relation="implements_logical_model")
    index._reindex()
    assert view_path("domain", "topic", "无线覆盖") in index.ancestors(billing.path)
    assert not organization_allowed_page(from_compiled(c).retrieval, billing.path, None, {"topic": "无线覆盖"})


def test_model_dependencies_stay_in_backend_graph():
    from enterprise_data_context.models import TypedReference
    fragments = sample_fragments()
    refs = next(f for f in fragments if f.candidate_name == "LTE_PERIODIC_MR" and f.section_type == "references")
    for relation in ("upstream", "downstream", "depends_on", "uses_model"):
        refs.references.append(TypedReference(relation, "BILLING_EVENTS", "physical-model", evidence=refs.evidence))
    c = ContextCompiler().compile_fragments(fragments)
    model = named(c, "LTE_PERIODIC_MR")
    assert {"upstream", "downstream", "depends_on", "uses_model"} <= {e["relation"] for e in c["graph"].neighbors(model.path, "out")}
    assert not any(e["parent_id"] == model.path and e["child_id"] == named(c, "BILLING_EVENTS").path for e in c["hierarchy"].edges)


def test_classifier_never_rejudges_explicit_tag_resolved_to_canonical_entity():
    c = compiled(); model = deepcopy(named(c, "UNKNOWN_MODEL")); topic = deepcopy(named(c, "RSRP"))
    topic.context_type = "topic"; topic.name = "无线覆盖"; topic.aliases = []
    topic.path = "data://topics/wireless-coverage"; topic.canonical_id = "topic:wireless-coverage"
    topic.sections = {}; topic.references = []
    model.sections["tags"] = [{"hierarchy_id": "domain", "kind": "topic", "label": "无线覆盖"}]
    model.evidence["tags"] = model.evidence["identity"]
    config = sample_config(); config.update(llm_enabled=True, llm_model="fixture")
    provider = Provider({"selected": "invented", "confidence": .99})
    index = HierarchyIndex(config, provider).project([model, topic])
    assert provider.calls == 0
    assert any(e["parent_id"] == topic.path and e["status"] == "CONFIRMED" for e in index.parents[model.path])
