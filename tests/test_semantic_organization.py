import json
from pathlib import Path
import subprocess
import sys

from jsonschema import Draft202012Validator

from enterprise_data_context.compiler import ContextCompiler
from enterprise_data_context.indexes.hierarchy import hierarchy_path
from enterprise_data_context.models import ContextFragment, Evidence, SourceLocation, TypedReference
from enterprise_data_context.persistence import save_compiled
from enterprise_data_context.runtime import from_compiled, load_runtime
from enterprise_data_context.tools import DataContextTools
from explore_agent import ExploreAgent


def evidence(source_id, section):
    return [Evidence(SourceLocation(source_id, f"{source_id}.json", section=section))]


def fragment(fragment_id, context_type, name, section, payload, source_id, references=None):
    return ContextFragment(
        fragment_id,
        context_type,
        name,
        section,
        payload,
        evidence=evidence(source_id, f"/{fragment_id}"),
        source_type="test",
        references=list(references or []),
    )


def semantic_fragments():
    app_ref = TypedReference(
        "part_of", "Railway Care", "topic",
        evidence=evidence("presales", "/features/0"),
    )
    metric_ref = TypedReference(
        "uses_metric", "RSRP", "metric",
        evidence=evidence("presales", "/features/0/metrics/0"),
    )
    logical_ref = TypedReference(
        "implements_logical_model", "Cell Coverage", "logical-model",
        evidence=evidence("catalog", "/tables/0/logical_model"),
    )
    return [
        fragment("app-id", "topic", "Railway Care", "identity", {"name": "Railway Care"}, "presales"),
        fragment("app-role", "topic", "Railway Care", "semantic_role", "application", "presales"),
        fragment("feature-id", "scenario", "High-speed Railway", "identity", {"name": "High-speed Railway"}, "presales"),
        fragment("feature-kind", "scenario", "High-speed Railway", "scenario.kind", "APP_FEATURE", "presales"),
        fragment(
            "feature-refs", "scenario", "High-speed Railway", "references", [], "presales",
            references=[app_ref, metric_ref],
        ),
        fragment("metric-id", "metric", "RSRP", "identity", {"name": "RSRP"}, "kpi"),
        fragment("metric-summary", "metric", "RSRP", "summary", "signal strength", "kpi"),
        fragment("object-id", "business-object", "Cell BE", "identity", {"name": "Cell BE"}, "sid"),
        fragment("logical-id", "logical-model", "Cell Coverage", "identity", {"name": "Cell Coverage"}, "modeling"),
        fragment("logical-layer", "logical-model", "Cell Coverage", "classification.layer", "ODI", "modeling"),
        fragment("logical-domain", "logical-model", "Cell Coverage", "topic_domain", "网络对象", "modeling"),
        fragment("logical-topic", "logical-model", "Cell Coverage", "topic", "小区", "modeling"),
        fragment("physical-id", "physical-model", "dws_cell_coverage", "identity", {"name": "dws_cell_coverage"}, "catalog"),
        fragment("physical-layer", "physical-model", "dws_cell_coverage", "classification.layer", "DWS", "catalog"),
        fragment("physical-domain", "physical-model", "dws_cell_coverage", "topic_domain", "Network Object", "catalog"),
        fragment("physical-topic", "physical-model", "dws_cell_coverage", "topic", "Cell", "catalog"),
        fragment("physical-object", "physical-model", "dws_cell_coverage", "primary_objects", ["Cell BE"], "catalog"),
        fragment(
            "physical-ref", "physical-model", "dws_cell_coverage", "references", [], "catalog",
            references=[logical_ref],
        ),
    ]


def test_semantic_hierarchy_and_cross_source_association_report():
    compiled = ContextCompiler().compile_fragments(semantic_fragments())
    contexts = {context.name: context for context in compiled["contexts"]}
    hierarchy = compiled["hierarchy"]

    feature = contexts["High-speed Railway"]
    app = contexts["Railway Care"]
    physical = contexts["dws_cell_coverage"]
    logical = contexts["Cell Coverage"]
    assert contexts["Cell BE"].evidence["identity"][0].source.source_id == "sid"

    feature_view = hierarchy.describe(feature.path)
    assert feature_view["parents"][0]["node"]["path"] == app.path
    assert [row["name"] for row in feature_view["breadcrumb"]] == [
        "Railway Care", "High-speed Railway",
    ]

    model_root = hierarchy_path("models", "ODI")
    topic_path = hierarchy_path("models", "ODI", "网络对象", "小区")
    assert hierarchy.has(model_root)
    assert {row["node"]["path"] for row in hierarchy.describe(topic_path)["children"]} == {
        logical.path, physical.path,
    }
    assert logical.path in {row["node"]["path"] for row in hierarchy.describe(physical.path)["parents"]}

    report = compiled["association_report"]
    schema = json.loads(
        (Path(__file__).parents[1] / "contracts" / "association-report.schema.json").read_text(
            encoding="utf-8"
        )
    )
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(report)
    assert report["references_by_status"] == {"CONFIRMED": 4}
    assert report["cross_source_confirmed_count"] == 3
    assert {
        (row["source"], row["relation"], row["target"])
        for row in report["cross_source_confirmed"]
    } == {
        (feature.path, "uses_metric", contexts["RSRP"].path),
        (physical.path, "implements_logical_model", logical.path),
        (physical.path, "maps_to_business_object", contexts["Cell BE"].path),
    }


def test_read_only_tools_expand_real_and_virtual_hierarchy_nodes():
    compiled = ContextCompiler().compile_fragments(semantic_fragments())
    tools = DataContextTools(from_compiled(compiled).retrieval)
    contexts = {context.name: context for context in compiled["contexts"]}
    feature_path = contexts["High-speed Railway"].path

    expanded = tools.data_expand([feature_path], ["parents", "related", "hierarchy"])[feature_path]
    assert expanded["parents"][0]["node"]["name"] == "Railway Care"
    assert any(edge["relation"] == "uses_metric" for edge in expanded["related"]["outgoing"])
    assert expanded["hierarchy"]["breadcrumb"][-1]["name"] == "High-speed Railway"

    model_root = hierarchy_path("models", "ODI")
    virtual = tools.data_read(model_root)
    assert virtual["level"] == "HIERARCHY"
    children = tools.data_expand([model_root], ["children"])[model_root]["children"]
    assert children[0]["node"]["name"] == "网络对象"

    search = tools.data_search("High-speed Railway", top_k=1)
    assert search["association_summary"]["cross_source_confirmed_count"] == 3

    bundle = ExploreAgent(tools).explore("High-speed Railway", top_k=1)
    assert bundle.analysis_context["hierarchy"][feature_path]["breadcrumb"][-1]["name"] == "High-speed Railway"
    assert any(
        edge["relation"] == "uses_metric"
        for edge in bundle.analysis_context["relations"][feature_path]["outgoing"]
    )


def test_hierarchy_and_association_report_survive_snapshot_reload(tmp_path):
    compiled = ContextCompiler().compile_fragments(semantic_fragments())
    manifest = save_compiled(compiled, tmp_path)
    runtime = load_runtime(tmp_path)
    assert manifest["schema_version"] == "1.3"
    assert manifest["coverage_declaration"]["status"] == "UNKNOWN"
    assert manifest["counts"]["hierarchy_nodes"] > len(compiled["contexts"])
    assert runtime.compiled["association_report"] == compiled["association_report"]

    physical = next(
        context for context in runtime.compiled["contexts"]
        if context.name == "dws_cell_coverage"
    )
    hierarchy = runtime.retrieval.data_read(physical.path)["hierarchy"]
    assert [row["name"] for row in hierarchy["breadcrumb"]][0:3] == [
        "ODI", "网络对象", "小区",
    ]


def test_offline_semantic_visualization_embeds_governed_snapshot(tmp_path):
    compiled = ContextCompiler().compile_fragments(semantic_fragments())
    save_compiled(compiled, tmp_path / "snapshot")
    output = tmp_path / "semantic-browser.html"

    completed = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).parents[1] / "scripts" / "generate_semantic_context_visualization.py"),
            "--snapshot", str(tmp_path / "snapshot"),
            "--output", str(output),
            "--title", "Semantic Browser",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    result = json.loads(completed.stdout)
    html = output.read_text(encoding="utf-8")

    assert result["pages"] == len(compiled["pages"])
    assert result["hierarchy_edges"] == compiled["hierarchy"].edge_count
    assert "Semantic Browser" in html
    assert "High-speed Railway" in html
    assert 'id="snapshot-data"' in html
    assert "Evidence" in html
    assert "浏览投影，不是本体" in html
