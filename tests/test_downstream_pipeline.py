import json
from dataclasses import asdict
from io import StringIO

import pytest
from jsonschema import Draft202012Validator

from enterprise_data_context.compiler import ContextCompiler
from enterprise_data_context.handoff import fragment_from_mapping, load_fragments
from enterprise_data_context.models import (
    ContextFragment,
    Evidence,
    SourceLocation,
    TypedReference,
)
from enterprise_data_context.adapters.mcp_stdio import DataContextMCPServer, serve_stdio
from enterprise_data_context.persistence import QualityGateError, save_compiled
from enterprise_data_context.runtime import from_compiled, load_runtime
from enterprise_data_context.tools import DataContextTools
from explore_agent import ExploreAgent
from explore_agent.evaluation import (
    EvaluationCase,
    EvaluationReport,
    GoldenGateError,
    assert_golden_gate,
    evaluate,
)


def ev(source_id, row):
    return [Evidence(SourceLocation(source_id, f"{source_id}.json", row=row))]


def downstream_fragments():
    return [
        ContextFragment("m-id", "metric", "RSRP", "identity", {"name": "RSRP"}, evidence=ev("kpi", 1), source_type="kpi_definition"),
        ContextFragment("m-summary", "metric", "RSRP", "summary", "无线信号强度", evidence=ev("kpi", 1), source_type="kpi_definition"),
        ContextFragment("m-formula-old", "metric", "RSRP", "formula", "OLD(RSRP)", evidence=ev("legacy", 2), source_type="unknown"),
        ContextFragment("m-formula", "metric", "RSRP", "formula", "AVG(RSRP)", evidence=ev("kpi", 1), source_type="kpi_definition"),
        ContextFragment(
            "m-ref", "metric", "RSRP", "references", [], evidence=ev("kpi", 1),
            source_type="kpi_definition",
            references=[TypedReference("supported_by", "LTE Periodic MR", "physical-model", evidence=ev("kpi", 1))],
        ),
        ContextFragment(
            "m-candidate", "metric", "RSRP", "formula", "P95(RSRP)", evidence=ev("llm", 9),
            source_type="semantic_assist", confidence=0.72, status="CANDIDATE",
        ),
        ContextFragment("p-id", "physical-model", "LTE Periodic MR", "identity", {"name": "LTE Periodic MR"}, evidence=ev("catalog", 3), source_type="asset_catalog"),
        ContextFragment("p-summary", "physical-model", "LTE Periodic MR", "summary", "LTE 周期 MR 明细", evidence=ev("catalog", 3), source_type="asset_catalog"),
        ContextFragment("p-fields", "physical-model", "LTE Periodic MR", "important_fields", ["CELL_ID", "RSRP"], evidence=ev("dictionary", 8), source_type="data_dictionary"),
        ContextFragment("p-grain", "physical-model", "LTE Periodic MR", "grain", ["Cell", "Time"], evidence=ev("catalog", 3), source_type="asset_catalog"),
    ]


def test_fragment_handoff_preserves_candidates_conflicts_and_bundle():
    compiled=ContextCompiler().compile_fragments(downstream_fragments())
    metric=next(x for x in compiled["contexts"] if x.name=="RSRP")
    assert metric.sections["formula"]=="AVG(RSRP)"
    assert metric.candidate_sections["formula"][0]["payload"]=="P95(RSRP)"
    assert metric.conflicts

    tools=DataContextTools(from_compiled(compiled).retrieval)
    search=tools.data_search("RSRP",top_k=1)
    assert {x["name"] for x in search["contexts"]}=={"RSRP","LTE Periodic MR"}
    model_path=next(x["path"] for x in search["contexts"] if x["name"]=="LTE Periodic MR")
    assert tools.data_expand([model_path],["fields"])[model_path]["fields"]==["CELL_ID","RSRP"]

    bundle=ExploreAgent(tools).explore("RSRP 有哪些现有模型可以提供？",top_k=1)
    assert bundle.conflicts
    assert bundle.candidates
    assert bundle.environment["binding_status"]=="unsupported"
    assert "environment_availability" in bundle.missing_context


def test_versioned_save_load_and_evaluation(tmp_path):
    compiled=ContextCompiler().compile_fragments(downstream_fragments())
    manifest=save_compiled(compiled,tmp_path)
    assert manifest["index_version"].startswith("context-")
    assert (tmp_path/"latest.json").exists()

    runtime=load_runtime(tmp_path)
    assert runtime.compiled["index_version"]==manifest["index_version"]
    bundle=ExploreAgent(runtime.retrieval).explore("RSRP 有哪些现有模型可以提供？",top_k=1)
    assert bundle.index_version==manifest["index_version"]
    assert any(x["name"]=="LTE Periodic MR" for x in bundle.primary_contexts)

    report=evaluate(ExploreAgent(runtime.retrieval),[
        EvaluationCase(
            "metric-model","RSRP 有哪些现有模型可以提供？",
            expected_contexts=["RSRP","LTE Periodic MR"],
            required_coverage=["metrics","models"],
        )
    ])
    assert report.passed==1
    assert report.context_recall==1.0


def test_candidate_identity_is_not_published_as_fact():
    compiled=ContextCompiler().compile_fragments([
        ContextFragment(
            "candidate-model","physical-model","LLM Guessed Model","identity",
            {"name":"LLM Guessed Model"},evidence=ev("llm",1),
            source_type="semantic_assist",confidence=0.61,status="CANDIDATE",
        )
    ])
    tools=DataContextTools(from_compiled(compiled).retrieval)
    assert tools.data_search("LLM Guessed Model")["contexts"]==[]
    assert any(x["code"]=="candidate_context_not_indexed" for x in compiled["quality_issues"])


def test_json_handoff_requires_evidence_and_preserves_status(tmp_path):
    row={
        "fragment_id":"f-1","context_type":"metric","candidate_name":"RSRP",
        "section_type":"summary","payload":"signal strength",
        "status":"DERIVED","confidence":0.8,"source_type":"kpi_definition",
        "evidence":[{"source":{"source_id":"kpi","path":"kpi.xlsx","sheet":"KPI","row":2}}],
    }
    fragment=fragment_from_mapping(row)
    assert fragment.status=="DERIVED"
    assert fragment.evidence[0].source.sheet=="KPI"
    handoff=tmp_path/"fragments.jsonl"
    handoff.write_text(json.dumps(row,ensure_ascii=False)+"\n",encoding="utf-8")
    assert load_fragments(handoff)[0].candidate_name=="RSRP"

    invalid=dict(row); invalid["evidence"]=[]
    try:
        fragment_from_mapping(invalid)
    except ValueError as exc:
        assert "evidence" in str(exc)
    else:
        raise AssertionError("missing evidence must be rejected")


def test_managed_bundle_budget_novelty_and_resume_state():
    compiled=ContextCompiler().compile_fragments(downstream_fragments())
    agent=ExploreAgent(DataContextTools(from_compiled(compiled).retrieval))

    first=agent.explore("RSRP 有哪些现有模型可以提供？",top_k=1,token_budget=500)
    assert first.policy["required_coverage"]==["metrics","models"]
    assert first.budget["estimated_tokens"] <= first.budget["token_budget"]
    assert first.selected_context_ids
    assert all(x["content_level"] in {"L0","L1"} for x in first.primary_contexts)
    assert all("content" not in x for x in first.analysis_context["metrics"])
    assert first.exploration_state["rounds"]==1
    assert first.stop_reason=="incomplete_after_focused_expand"
    assert "environment_availability" in first.missing_context

    second=agent.explore(
        "RSRP 有哪些现有模型可以提供？",
        top_k=1,
        token_budget=500,
        state=first.exploration_state,
    )
    assert not (set(first.selected_context_ids) & set(second.selected_context_ids))
    assert second.novelty["seen_skipped_count"] >= 1
    assert "seen_context" in second.truncation_reasons
    assert second.exploration_state["rounds"]==2
    assert second.stop_reason=="no_new_context"

    tiny=agent.explore("RSRP",top_k=1,token_budget=1)
    assert tiny.primary_contexts==[]
    assert tiny.stop_reason=="token_budget_exhausted"
    assert "token_budget" in tiny.truncation_reasons


def test_exploration_state_is_pinned_to_index_version(tmp_path):
    compiled=ContextCompiler().compile_fragments(downstream_fragments())
    save_compiled(compiled,tmp_path)
    runtime=load_runtime(tmp_path)
    agent=ExploreAgent(runtime.retrieval)
    bundle=agent.explore("RSRP",top_k=1)
    stale=dict(bundle.exploration_state)
    stale["index_version"]="context-stale"
    with pytest.raises(ValueError,match="index_version"):
        agent.explore("RSRP",top_k=1,state=stale)


def test_quality_and_golden_release_gates(tmp_path):
    compiled=ContextCompiler().compile_fragments(downstream_fragments())
    compiled["quality_issues"].append({"severity":"error","code":"forced-test-error"})
    with pytest.raises(QualityGateError,match="forced-test-error"):
        save_compiled(compiled,tmp_path)
    assert not (tmp_path/"latest.json").exists()

    failed=EvaluationReport(1,0,0.5,0.5,[{"case_id":"failed","passed":False}])
    with pytest.raises(GoldenGateError,match="golden gate rejected"):
        assert_golden_gate(failed)


def test_mcp_adapter_exposes_only_four_read_only_tools():
    compiled=ContextCompiler().compile_fragments(downstream_fragments())
    server=DataContextMCPServer(from_compiled(compiled).retrieval)
    initialized=server.handle({
        "jsonrpc":"2.0","id":1,"method":"initialize",
        "params":{
            "protocolVersion":"2025-11-25","capabilities":{},
            "clientInfo":{"name":"test","version":"1"},
        },
    })
    assert initialized["result"]["capabilities"]=={"tools":{"listChanged":False}}
    server.handle({"jsonrpc":"2.0","method":"notifications/initialized"})
    listed=server.handle({"jsonrpc":"2.0","id":2,"method":"tools/list"})
    assert {x["name"] for x in listed["result"]["tools"]}==DataContextTools.ALLOWED

    called=server.handle({
        "jsonrpc":"2.0","id":3,"method":"tools/call",
        "params":{"name":"data_search","arguments":{"query":"RSRP","top_k":1}},
    })
    assert called["result"]["isError"] is False
    assert called["result"]["structuredContent"]["contexts"]

    stream=StringIO("\n".join(json.dumps(x) for x in [
        {
            "jsonrpc":"2.0","id":1,"method":"initialize",
            "params":{
                "protocolVersion":"2025-11-25","capabilities":{},
                "clientInfo":{"name":"test","version":"1"},
            },
        },
        {"jsonrpc":"2.0","method":"notifications/initialized"},
        {"jsonrpc":"2.0","id":2,"method":"tools/list"},
    ])+"\n")
    output=StringIO()
    serve_stdio(DataContextMCPServer(from_compiled(compiled).retrieval),stream,output)
    messages=[json.loads(line) for line in output.getvalue().splitlines()]
    assert [message["id"] for message in messages]==[1,2]


def test_context_bundle_contract_declares_governance_fields():
    schema=json.loads(
        open("contracts/context-bundle.schema.json",encoding="utf-8").read()
    )
    required=set(schema["required"])
    assert {"policy","budget","novelty","exploration_state"} <= required
    Draft202012Validator.check_schema(schema)

    compiled=ContextCompiler().compile_fragments(downstream_fragments())
    bundle=ExploreAgent(from_compiled(compiled).retrieval).explore("RSRP",top_k=1)
    assert required <= set(asdict(bundle))
    Draft202012Validator(schema).validate(asdict(bundle))
