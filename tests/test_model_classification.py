from enterprise_data_context.classification import (
    classification_scope,
    classify_model,
    load_classification_catalog,
)
from enterprise_data_context.compiler import ContextCompiler
from enterprise_data_context.models import ContextFragment, Evidence, SourceLocation
from enterprise_data_context.runtime import from_compiled
from enterprise_data_context.tools import DataContextTools
from explore_agent.router import QueryRouter


def evidence(name):
    return [Evidence(SourceLocation(name, f"{name}.json", section="/tables/0"))]


def model_fragments(name, layer, domain, topic):
    rows = []
    for section, payload in (
        ("identity", {"name": name}),
        ("summary", f"{name} model"),
        ("classification.layer", layer),
        ("topic_domain", domain),
        ("topic", topic),
    ):
        rows.append(ContextFragment(
            f"{name}-{section}", "physical-model", name, section, payload,
            evidence=evidence(name), source_type="asset_catalog",
        ))
    return rows


def test_four_formal_layers_and_warehouse_aliases():
    catalog = load_classification_catalog()
    assert catalog["formal_layers"] == ["ODS", "SDL", "ODI", "ADS"]

    sdl = classify_model("DWD", "Performance", "Wireless Coverage")
    assert sdl["layer"]["canonical"] == "SDL"
    assert sdl["layer"]["status"] == "APPROXIMATE_ALIAS"
    assert sdl["topic_domain"]["canonical"] == "性能"
    assert sdl["topic"]["canonical"] == "无线覆盖"
    assert sdl["status"] == "NORMALIZED"

    odi = classify_model("DWS", "网络对象", "Cell")
    assert odi["layer"]["canonical"] == "ODI"
    assert odi["topic"]["canonical"] == "小区"


def test_layer_aware_validation_preserves_ambiguous_values():
    result = classify_model("对象洞察层", "网络体验域数据模型", "用户宽表")
    assert result["layer"]["canonical"] == "ODI"
    assert result["topic_domain"]["canonical"] is None
    assert result["topic"]["canonical"] is None
    assert {issue["code"] for issue in result["issues"]} == {
        "unknown_topic_domain", "topic_domain_unresolved",
    }

    planning = classify_model("SDL", "规划", "楼宇")
    assert planning["issues"][0]["code"] == "topic_catalog_incomplete"


def test_router_and_page_index_use_keyed_governed_facets():
    assert classification_scope("查找 SDL 业务域 VoLTE 模型") == {
        "layer": "SDL", "topic_domain": "业务", "topic": "VoLTE",
    }
    routed = QueryRouter().route("查找 DWS 网络对象小区模型")
    assert {"layer": "ODI", "topic_domain": "网络对象", "topic": "小区"}.items() <= routed.items()

    fragments = model_fragments("volte_daily", "SDL", "业务", "VoLTE")
    fragments += model_fragments("coverage_daily", "SDL", "性能", "无线覆盖")
    compiled = ContextCompiler().compile_fragments(fragments)
    tools = DataContextTools(from_compiled(compiled).retrieval)
    result = tools.data_search(
        "daily model", scope={"layer": "SDL", "topic_domain": "业务", "topic": "VoLTE"}, top_k=4,
    )
    assert [row["name"] for row in result["contexts"]] == ["volte_daily"]

    metric = ContextFragment(
        "volte-drop", "metric", "VoLTE掉话率", "summary", "VoLTE call drop rate",
        evidence=evidence("volte-drop"), source_type="kpi_definition",
    )
    mixed = ContextCompiler().compile_fragments(fragments + [metric])
    routed_scope = QueryRouter().route("VoLTE掉话率")
    mixed_result = DataContextTools(from_compiled(mixed).retrieval).data_search(
        "VoLTE掉话率", scope=routed_scope, top_k=4,
    )
    assert "VoLTE掉话率" in {row["name"] for row in mixed_result["contexts"]}


def test_quality_gate_reports_noncanonical_model_classification():
    fragments = model_fragments("bad_model", "DWD", "Unknown Domain", "Unknown Topic")
    compiled = ContextCompiler().compile_fragments(fragments)
    codes = {issue["code"] for issue in compiled["quality_issues"]}
    model = compiled["contexts"][0]
    assert model.sections["classification.layer"] == "SDL"
    assert model.sections["classification.layer_raw"] == "DWD"
    assert "topic_domain" not in model.sections
    assert model.candidate_sections["topic_domain"][0]["payload"] == "Unknown Domain"
    assert "unknown_topic_domain" in codes
    assert "topic_domain_unresolved" in codes
