from copy import deepcopy
from dataclasses import asdict
import json
from pathlib import Path
import pytest
from jsonschema import Draft202012Validator

from enterprise_data_context.compiler import ContextCompiler
from enterprise_data_context.hierarchy_config import validate_hierarchy_config
from enterprise_data_context.indexes.hierarchy import HierarchyIndex, view_path
from enterprise_data_context.materialization.aggregate_pages import aggregate_uri
from enterprise_data_context.models import CanonicalContext, Evidence, SourceLocation
from enterprise_data_context.persistence import save_compiled, load_compiled, QualityGateError
from enterprise_data_context.retrieval_strategy import strategy, validate_strategy
from enterprise_data_context.runtime import from_compiled
from evaluation.hierarchy.sample import sample_config, sample_fragments
from evaluation.hierarchy.semantic_fixture import build_semantic_fixture, SEMANTIC_CASES, FixtureSemanticEncoder
from explore_agent import ExploreAgent
from explore_agent.router import QueryRouter


def compiled():
    return ContextCompiler(hierarchy_config=sample_config()).compile_fragments(sample_fragments())


def taxonomy():
    return {"version": "taxonomy-test/v1", "inference_enabled": False,
        "taxonomy_nodes": [
            {"id": "performance", "view": "domain", "kind": "topic-domain", "label": "Performance"},
            {"id": "coverage", "view": "domain", "kind": "topic", "label": "Wireless Coverage", "aliases": ["Coverage"]},
            {"id": "billing", "view": "domain", "kind": "topic-domain", "label": "Billing"},
            {"id": "invoice", "view": "domain", "kind": "topic", "label": "Invoice"}],
        "taxonomy_edges": [{"parent": parent, "child": child, "status": "CONFIRMED",
            "provenance": {"method": "explicit_taxonomy", "source": "modeling_standard"},
            "evidence": [{"source": {"source_id": "standard", "path": "standards/taxonomy.json", "row": i}}]}
            for i, (parent, child) in enumerate((("performance", "coverage"), ("billing", "invoice")), 1)]}


def test_applicable_metric_and_non_applicable_gate():
    c = compiled(); index = c["hierarchy"]
    metric = next(c for c in c["contexts"] if c.name == "RSRP")
    result = index.classification(metric.path)
    assert result["applicable_views"] == ["analysis"]
    assert result["status"] == "classified"
    assert result["missing_views"] == []
    metric = deepcopy(metric)
    metric.sections = {"tags": [{"hierarchy_id": "asset", "kind": "layer", "label": "ODS"}]}
    metric.references = []; metric.evidence["tags"] = metric.evidence["identity"]
    invalid = HierarchyIndex().project([metric])
    assert "entity_placed_in_non_applicable_view" in {i["code"] for i in invalid.validate()}
    assert invalid.classification(metric.path)["status"] == "unclassified"


def test_canonical_and_aggregate_uris_are_separate_at_every_level(tmp_path):
    c = compiled()
    topic = CanonicalContext("topic:coverage", "topic", "无线覆盖", "data://topics/coverage")
    topic.sections = {"summary": "canonical topic"}
    topic.evidence = {"identity": [Evidence(SourceLocation("catalog", "topic.json"))]}
    # Compile a page through the existing producer rather than inserting fake serving state.
    from enterprise_data_context.models import ContextFragment
    extra = [ContextFragment("topic-id", "topic", topic.name, "identity", {"name": topic.name}, evidence=topic.evidence["identity"])]
    c = ContextCompiler(hierarchy_config=sample_config()).compile_fragments(sample_fragments() + extra)
    topic = next(x for x in c["contexts"] if x.context_type == "topic")
    index = c["hierarchy"]; service = from_compiled(c).retrieval
    uri = aggregate_uri(index, topic.path, "domain")
    assert uri != topic.path and topic.path not in index.aggregate_pages
    assert uri not in service.pages
    for level in ("L0", "L1", "L2"):
        read = service.data_read(uri, level)
        assert read["context_type"] == "aggregate-context" and read["level"] == level
        assert read["canonical_ref"] == topic.path
        assert service.data_read(topic.path, level).get("context_type") != "aggregate-context"
    assert service.data_expand([uri], ["aggregate"])[uri]["aggregate"]["context_type"] == "aggregate-context"
    save_compiled(c, tmp_path)
    restored = from_compiled(load_compiled(tmp_path)).retrieval
    assert restored.data_read(uri, "L2") == service.data_read(uri, "L2")


def test_sparse_explicit_taxonomy_without_any_entity_and_precedence():
    config = taxonomy(); index = HierarchyIndex(config).project([])
    assert len(index.edges) == 2
    assert all(e["status"] == "CONFIRMED" and e["active"] and e["provenance"]["method"] == "explicit_taxonomy" for e in index.edges)
    assert not [i for i in index.validate() if i["severity"] == "error"]
    model = CanonicalContext("model:m", "physical-model", "M", "data://physical-models/m",
        sections={"topic_domain": "Conflicting", "topic": "Coverage"})
    ev = Evidence(SourceLocation("instance", "m.json"))
    model.evidence = {k: [ev] for k in model.sections}
    index.update([model])
    coverage = view_path("domain", "topic", "Wireless Coverage")
    incoming = index.parents[coverage]
    assert len(incoming) == 2
    assert all(e["active"] == (e["provenance"]["method"] == "explicit_taxonomy") for e in incoming)
    assert index.conflicts
    assert not [i for i in index.validate() if i["severity"] == "error"]
    schema = json.loads(Path("contracts/semantic-hierarchy-edge.schema.json").read_text())
    for edge in index.edges:
        Draft202012Validator(schema).validate(edge)


@pytest.mark.parametrize("mutation,code", [
    (lambda c: c["taxonomy_edges"][0].update(child="absent"), "unknown_taxonomy_node"),
    (lambda c: c["taxonomy_edges"][0].update(evidence=[]), "invalid_taxonomy_edge"),
    (lambda c: c["taxonomy_edges"].append({**deepcopy(c["taxonomy_edges"][0]), "parent": "coverage", "child": "performance"}), "taxonomy_cycle"),
])
def test_taxonomy_invalid_config_rejected(mutation, code):
    config = taxonomy(); mutation(config)
    with pytest.raises(ValueError, match=code):
        validate_hierarchy_config(config)


@pytest.mark.parametrize("query,mode,view", [
    ("RSRP有哪些模型？", "direct", None),
    ("LTE_PERIODIC_MR支持哪些分析？", "direct", None),
    ("地铁弱覆盖需要哪些数据？", "hierarchical", "analysis"),
    ("有哪些数据描述网络资源配置？", "hierarchical", "domain"),
    ("ODS层有哪些无线模型？", "hierarchical", "asset"),
    ("RSRP用于弱覆盖时还需要哪些数据？", "hybrid", "analysis"),
    ("LTE_PERIODIC_MR在无线覆盖场景中还能支撑哪些指标？", "hybrid", "analysis"),
])
def test_golden_strategy_in_router_and_serving(query, mode, view):
    route = QueryRouter().analyze(query)
    assert route["retrieval_strategy"]["mode"] == mode
    assert route["retrieval_strategy"]["primary_view"] == view
    bundle = ExploreAgent(from_compiled(compiled()).retrieval).explore(query)
    trace = bundle.retrieval_trace
    assert trace["mode"] == mode and trace["hierarchy_view"] == view
    validate_strategy(trace["retrieval_strategy"])
    assert trace["confidence"] > 0 and trace["reasons"]
    assert bundle.telemetry["tool_calls"] <= 2
    if mode == "direct":
        assert trace["branch_candidates"] == trace["selected_branches"] == []


@pytest.mark.parametrize("intent,view", [
    ("scenario_exploration", "analysis"), ("business_semantic_understanding", "domain"),
    ("model_classification", "domain"), ("field_discovery", "asset"), ("model_inventory", "asset")])
def test_structured_intent_selects_view_without_lexical_hints(intent, view):
    result = strategy("show me more", intent=intent)
    assert result["primary_view"] == view
    result = strategy("show me more", intent=intent, scope={"topic": "T"}, aspects=["fields"])
    assert len(result["hierarchy_views"]) <= 2
    bad = {**result, "hierarchy_views": ["invented"], "primary_view": "invented"}
    with pytest.raises(ValueError):
        validate_strategy(bad)


def test_nonlexical_hybrid_branch_recall_and_no_l2_embedding():
    c = build_semantic_fixture(); index = c["hierarchy"].aggregate_index
    for query, branch in SEMANTIC_CASES:
        lexical = index.search(query, ["analysis"], method="lexical")
        hybrid = index.search(query, ["analysis"], method="hybrid")
        assert not lexical
        assert c["hierarchy"].aggregate_pages[hybrid[0]["path"]]["name"] == branch
        assert hybrid[0]["score_breakdown"]["dense"] > .9
        assert hybrid[0]["score_breakdown"]["rrf"] > 0
        assert set(hybrid[0]["placement_quality"]) == {"confirmed", "derived", "candidate"}
    assert not index.search(SEMANTIC_CASES[0][0], ["domain"])
    for page in index.indexes["analysis"].pages.values():
        assert page.l2 == {} and '"members"' not in page.l1 and '"evidence"' not in page.l1


def test_taxonomy_edge_incremental_no_entity_inference_and_unrelated_branch_stable():
    config = taxonomy(); index = HierarchyIndex(config).project([])
    billing = view_path("domain", "topic-domain", "Billing")
    original = index.aggregate_pages[billing]
    config = deepcopy(index.config)
    config["taxonomy_edges"][0]["evidence"][0]["source"]["row"] = 9
    index.config = config; index.update([])
    assert index.last_update["rebuilt_entities"] == [] and index.last_update["inference_calls"] == 0
    assert index.aggregate_pages[billing] is original
    assert billing not in index.last_update["rebuilt_aggregates"]
    index.update([])
    assert not index.last_update["rebuilt_aggregates"]
    assert not index.aggregate_index.last_changed


def test_snapshot_policy_fingerprint_and_stale_index_gates(tmp_path):
    c = compiled(); index = c["hierarchy"]
    original = index.to_dict()
    old = deepcopy(original); old["version"] = "semantic-hierarchy/v1"
    with pytest.raises(ValueError, match="rebuild"):
        HierarchyIndex.from_dict(old, c["contexts"])
    mutated = deepcopy(original); mutated["config"]["routing_policy_version"] = "other"
    with pytest.raises(ValueError, match="fingerprint"):
        HierarchyIndex.from_dict(mutated, c["contexts"])
    manifest = save_compiled(c, tmp_path)
    index.config["routing_policy_version"] = "policy-update"
    index.update(c["contexts"])
    assert not index.last_update["rebuilt_entities"]
    assert not index.last_update["rebuilt_aggregates"]
    assert save_compiled(c, tmp_path)["index_version"] != manifest["index_version"]
    aggregate = next(iter(index.aggregate_pages.values()))
    aggregate["L0"] += " changed without indexing"
    assert "aggregate_index_stale" in {i["code"] for i in index.validate()}
    with pytest.raises(QualityGateError, match="aggregate_index_stale"):
        save_compiled(c, tmp_path)
    aggregate["path"] = "data://views/invalid/topic/x"
    assert "view_uri_mismatch" in {i["code"] for i in index.validate()}
    canonical = c["contexts"][0].path
    index.aggregate_pages[canonical] = aggregate
    assert "page_path_collision" in {i["code"] for i in index.validate()}


def test_candidate_only_branch_excluded_and_candidate_not_classified():
    c = compiled(); index = c["hierarchy"]
    model = next(x for x in c["contexts"] if x.name == "UNKNOWN_MODEL")
    provenance = {"method": "neighbor_inference", "inference": {"candidate_set": ["Candidate"], "selected": "Candidate",
        "supporting_features": {}, "supporting_context_ids": [model.path], "model": None, "prompt_version": "test", "confidence": .9}}
    index._add_placement(model, "domain", "topic", "Candidate", "CANDIDATE", .9,
                         [asdict(e) for e in model.evidence["identity"]], provenance)
    index._reindex()
    from enterprise_data_context.materialization.aggregate_pages import materialize_aggregate
    for page in materialize_aggregate(index, view_path("domain", "topic", "Candidate")):
        index.aggregate_pages[page["path"]] = page
    index.aggregate_index.sync(index.aggregate_pages)
    assert view_path("domain", "topic", "Candidate") not in index.aggregate_index.fingerprints
    status = index.classification(model.path)
    assert "domain" in status["candidate_views"] and "domain" in status["missing_views"]
    edge = next(e for e in index.edges if e["child_id"] == model.path and e["status"] == "CANDIDATE")
    edge["active"] = True
    assert "candidate_as_classified" in {i["code"] for i in index.validate()}


def test_semantic_branches_feed_bundle_in_one_search_operation():
    c = build_semantic_fixture(); agent = ExploreAgent(from_compiled(c).retrieval)
    for i, (query, _) in enumerate(SEMANTIC_CASES):
        bundle = agent.explore(query, top_k=1, token_budget=5000)
        expected = next(x.path for x in c["contexts"] if x.name == "DATA_" + str(i))
        assert expected in bundle.selected_context_ids
        assert bundle.retrieval_trace["mode"] == "hierarchical"
        assert bundle.telemetry["tool_calls"] <= 2


def test_bounded_semantic_router_can_supply_rich_intent_but_not_unknown_schema():
    class Provider:
        def complete(self, *, task, **kwargs):
            return {"intent": "business_semantic_understanding", "entities": [], "aspects": []}
    result = QueryRouter(Provider()).analyze("解释这些资源的业务意义")
    assert result["retrieval_strategy"]["primary_view"] == "domain"
    assert result["intent"] == "business_semantic_understanding"
    class Invalid:
        def complete(self, *, task, **kwargs):
            return {"intent": "business_semantic_understanding", "entities": [], "aspects": [], "view": "invented"}
    router = QueryRouter(Invalid())
    result = router.analyze("解释这些资源的业务意义")
    assert result["intent"] == "generic"


def test_aggregate_encoder_incremental_reuses_unchanged_documents():
    c = build_semantic_fixture(); index = c["hierarchy"].aggregate_index
    class CountingEncoder(FixtureSemanticEncoder):
        def __init__(self): self.batches = []
        def encode(self, texts):
            self.batches.append(texts)
            return super().encode(texts)
    encoder = CountingEncoder(); index.encoder.encoder = encoder
    index.search(SEMANTIC_CASES[0][0], ["analysis"])
    encoder.batches = []
    pages = deepcopy(c["hierarchy"].aggregate_pages)
    path = next(p for p, a in pages.items() if a["name"] == "Mobility")
    pages[path]["L0"] += "; updated overview"
    index.sync(pages)
    assert index.last_changed == [path]
    index.search(SEMANTIC_CASES[0][0], ["analysis"])
    document_batches = [b for b in encoder.batches if b != [SEMANTIC_CASES[0][0]]]
    assert len(document_batches) == 1 and len(document_batches[0]) == 1


def test_taxonomy_move_updates_old_new_ancestors_and_survives_reload():
    index = HierarchyIndex(taxonomy()).project([])
    config = deepcopy(index.config)
    config["taxonomy_edges"][0]["parent"] = "billing"
    index.config = config; index.update([])
    performance = view_path("domain", "topic-domain", "Performance")
    billing = view_path("domain", "topic-domain", "Billing")
    assert index.aggregate_pages[performance]["child_branches"] == []
    assert len(index.aggregate_pages[billing]["child_branches"]) == 2  # explicit leaf groups have addressable aggregate pages
    assert len(index.children[billing]) == 2
    restored = HierarchyIndex.from_dict(index.to_dict(), [])
    restored.update([])
    assert not restored.last_update["rebuilt_aggregates"]
    assert not restored.validate()


def test_strategy_schema_matches_mcp_and_dense_failure_is_explicit():
    from enterprise_data_context.adapters.mcp_stdio import TOOL_DEFINITIONS
    schema = json.loads(Path("contracts/retrieval-strategy.schema.json").read_text())
    assert TOOL_DEFINITIONS[0]["inputSchema"]["properties"]["retrieval_strategy"] == schema
    for intent in ("scenario_exploration", "business_object_exploration", "model_inventory"):
        Draft202012Validator(schema).validate(strategy("show details", intent=intent))
    c = build_semantic_fixture(); index = c["hierarchy"].aggregate_index
    class Broken:
        version = "unavailable"
        def encode(self, texts): raise RuntimeError("offline")
    index.encoder.encoder = Broken()
    hits = index.search("Mobility", ["analysis"])
    assert hits and hits[0]["score_breakdown"]["exact"] == 1
    assert index.last_warnings[0]["code"] == "vector_retrieval_unavailable"


def test_config_schema_and_leaf_view_page_are_explicit():
    schema = json.loads(Path("contracts/semantic-hierarchy-config.schema.json").read_text())
    for value in (taxonomy(), json.loads(Path("config/semantic-hierarchy.sample.json").read_text())):
        Draft202012Validator(schema).validate(value)
        validate_hierarchy_config(value)
    index = HierarchyIndex(taxonomy()).project([])
    from enterprise_data_context.materialization.aggregate_pages import read_aggregate
    leaf = view_path("domain", "topic", "Invoice")
    for level in ("L0", "L1", "L2"):
        assert read_aggregate(index, leaf, level)["context_type"] == "aggregate-context"


def test_taxonomy_label_update_reprojects_rule_placements():
    config = taxonomy()
    config.update(inference_enabled=True,
        taxonomy=[{"id": "rule-label", "view": "domain", "kind": "topic", "label": "Coverage"}],
        rules=[{"id": "metric-rule", "selected": "rule-label", "when": {"metrics": ["M"]}}])
    model = CanonicalContext("model:m", "physical-model", "M_DATA", "data://physical-models/m-data",
                             sections={"metrics": ["M"]}, evidence={"metrics": [Evidence(SourceLocation("model", "model.json"))]})
    index = HierarchyIndex(config).project([model])
    old = view_path("domain", "topic", "Wireless Coverage")
    assert any(e["parent_id"] == old for e in index.parents[model.path])
    index.config["taxonomy_nodes"][1]["label"] = "Radio Coverage"
    index.update([model])
    new = view_path("domain", "topic", "Radio Coverage")
    assert any(e["parent_id"] == new for e in index.parents[model.path])
    assert not any(e["parent_id"] == old for e in index.parents[model.path])
    assert not [i for i in index.validate() if i["severity"] == "error"]
