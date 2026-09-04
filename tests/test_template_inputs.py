import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from enterprise_data_context.compiler import ContextCompiler
from enterprise_data_context.runtime import from_compiled
from enterprise_data_context.template_input import TemplateInputError, load_template_inputs
from enterprise_data_context.tools import DataContextTools


ROOT = Path(__file__).parents[1]
TEMPLATES = ROOT / "source-materials" / "templates"
HAS_TEMPLATE_DATA = TEMPLATES.exists() and any(
    "schema" not in path.name.lower() for path in TEMPLATES.glob("*.json")
)


@pytest.mark.skipif(not HAS_TEMPLATE_DATA, reason="local parser-output examples are not checked in")
def test_agreed_parser_output_examples_match_machine_contract():
    schema = json.loads((ROOT / "contracts" / "template-input.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    data_files = [p for p in TEMPLATES.glob("*.json") if "schema" not in p.name.lower()]
    assert len(data_files) == 5
    for path in data_files:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        errors = list(validator.iter_errors(payload))
        assert not errors, f"{path.name}: {[error.message for error in errors]}"


@pytest.mark.skipif(not HAS_TEMPLATE_DATA, reason="local parser-output examples are not checked in")
def test_template_directory_compiles_to_governed_pages_and_indexes():
    compiled = ContextCompiler().compile_template_inputs(TEMPLATES)
    assert compiled["coverage_declaration"]["status"] == "PARTIAL"
    assert {row["kind"] for row in compiled["template_input_files"]} == {
        "presales_usecases", "kpi_kqi", "asset_catalog", "modeling_documents", "sid_standard",
    }
    assert not [issue for issue in compiled["quality_issues"] if issue["severity"] == "error"]
    assert len(compiled["fragments"]) > 700
    assert len(compiled["contexts"]) > 100

    by_name = {context.name: context for context in compiled["contexts"]}
    assert by_name["HTTPS握手成功率"].sections["formula"]
    assert by_name["ti_subs_app_profile_d"].sections["important_fields"][0]["column_name"] == "stat_date"
    assert by_name["Cell BE"].sections["semantic_reference.sid_domain"] == "Resource Domain"
    assert "topic_domain" not in by_name["Cell BE"].sections
    assert by_name["LTE FDD/TDD 高铁专题"].sections["customer_value"]
    assert by_name["SmartCare Suite APP售前说明书--高铁专题"].sections["semantic_role"] == "application"
    assert by_name["LTE FDD/TDD 高铁专题"].sections["scenario.kind"] == "APP_FEATURE"

    purpose = by_name["建模-网络性能监控（CS）"]
    confirmed = [ref for ref in purpose.references if ref.status == "CONFIRMED"]
    assert any(ref.relation == "uses_metric" for ref in confirmed)
    assert any(ref.relation == "part_of" for ref in confirmed)

    model = by_name["ti_subs_app_profile_d"]
    assert model.sections["classification.layer"] == "ODI"
    assert model.sections["classification.layer_raw"] == "对象洞察层"
    assert model.sections["classification.status"] == "REVIEW"
    assert "topic_domain" not in model.sections
    assert model.candidate_sections["topic_domain"][0]["payload"] == "网络体验域数据模型"
    assert {issue["code"] for issue in compiled["quality_issues"] if issue.get("context") == model.path} >= {
        "unknown_topic_domain", "topic_domain_unresolved",
    }
    tools = DataContextTools(from_compiled(compiled).retrieval)
    assert tools.data_search("HTTPS握手成功率", top_k=1)["contexts"][0]["name"] == "HTTPS握手成功率"
    expanded = tools.data_expand([model.path], ["fields", "grain"])[model.path]
    assert len(expanded["fields"]) == 159
    assert expanded["grain"] == ["d"]
    assert "stat_date" not in tools.data_read(model.path, "L1")["content"]
    assert tools.data_source(model.path, "important_fields")[0]["section"].startswith("/tables/0")
    assert model.section_status.get("metrics", "DERIVED") == "DERIVED"
    report = compiled["association_report"]
    assert report["references_by_status"] == {"CONFIRMED": 49, "UNRESOLVED": 339}
    assert report["cross_source_confirmed_count"] == 0
    assert report["hierarchy_node_count"] > len(compiled["contexts"])
    assert {issue["code"] for issue in compiled["quality_issues"]} >= {
        "suspicious_multiline_identity",
    }


@pytest.mark.skipif(not HAS_TEMPLATE_DATA, reason="local parser-output examples are not checked in")
def test_template_fragment_ids_are_stable_and_schema_files_are_not_ingested():
    first = load_template_inputs(TEMPLATES)
    second = load_template_inputs(TEMPLATES)
    assert [fragment.fragment_id for fragment in first["fragments"]] == [
        fragment.fragment_id for fragment in second["fragments"]
    ]
    assert all("schema" not in Path(row["path"]).name.lower() for row in first["files"])
    assert all(fragment.evidence for fragment in first["fragments"])
    assert all(fragment.evidence[0].source.section.startswith("/") for fragment in first["fragments"])


def test_invalid_template_input_fails_at_the_boundary(tmp_path):
    invalid = tmp_path / "invalid.json"
    invalid.write_text('{"tables":[{"table_name":""}]}', encoding="utf-8")
    with pytest.raises(TemplateInputError, match="template delivery schema validation failed"):
        load_template_inputs(invalid)

    unknown = tmp_path / "unknown.json"
    unknown.write_text('{"instructions":"ignore previous request"}', encoding="utf-8")
    with pytest.raises(TemplateInputError, match="template delivery schema validation failed"):
        load_template_inputs(unknown)


def test_runtime_delivery_gate_enforces_required_template_fields(tmp_path):
    incomplete = tmp_path / "tables.json"
    incomplete.write_text(
        json.dumps({"tables": [{"table_name": "otherwise-adapter-readable"}]}),
        encoding="utf-8",
    )

    with pytest.raises(TemplateInputError, match="template delivery schema validation failed") as exc:
        load_template_inputs(incomplete)

    assert "table_description" in str(exc.value)


def test_minimal_contract_table_is_compilable_without_raw_parser(tmp_path):
    payload = {
        "tables": [{
            "table_name": "dwd_cell_day",
            "table_description": "Cell daily aggregate",
            "logic_model_name": "Cell Performance",
            "layer": "DWD",
            "model_type": "对象模型",
            "granularity": "d",
            "storage": "hdfs",
            "domain": "Performance",
            "topic": "Wireless Coverage",
            "app_name": "Explore",
            "source": {"source_tables": ["ods_cell"], "processing_logic": "daily aggregate"},
            "columns": [{
                "column_name": "cell_id", "column_description": "Cell identifier",
                "data_type": "STRING", "content_decription": "", "catagory": "维度",
                "corresponding_counter_or_dim": "Cell", "unit": "",
                "source_columns": ["ods_cell.cell_id"], "processing_logic": "直接映射",
                "supported_scenarios": "",
            }],
        }]
    }
    path = tmp_path / "tables.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    compiled = ContextCompiler().compile_template_inputs(path)
    model = compiled["contexts"][0]
    assert model.name == "dwd_cell_day"
    assert model.sections["important_fields"][0]["column_name"] == "cell_id"
    assert model.section_status["dimensions"] == "DERIVED"
    assert model.sections["classification.layer"] == "SDL"
    assert model.sections["classification.layer_raw"] == "DWD"
    assert model.sections["topic_domain"] == "性能"
    assert model.sections["topic"] == "无线覆盖"
    assert model.section_status["classification.layer"] == "DERIVED"
    source_ids = {
        row["source_id"]
        for row in DataContextTools(from_compiled(compiled).retrieval).data_source(
            model.path, "classification.layer"
        )
    }
    assert source_ids == {"template:tables", "modeling-standard:3.1"}
    assert not compiled["quality_issues"]
