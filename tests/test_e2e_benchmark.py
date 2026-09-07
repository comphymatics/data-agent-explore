from dataclasses import asdict
import csv
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest
import yaml

from evaluation.benchmark.raw_corpus import freeze, inventory, fingerprint, verify
from evaluation.benchmark.result_contract import BenchmarkCase, QueryBudget, RunContext, BuildResult, QueryResult, SYSTEMS
from evaluation.benchmark.usage import tokens, tool_counts
from evaluation.benchmark.entity_scoring import score
from evaluation.normalization.entity_registry import EntityRegistry
from evaluation.normalization.normalizer import normalize
from evaluation.benchmark.e2e_runner import run, ADAPTERS
from evaluation.benchmark.adapters.data_explore import DataExploreAdapter
from evaluation.benchmark.adapters.llm_wiki import LLMWikiAdapter
from evaluation.benchmark.adapters.opencode_native import exported_calls, OpenCodeNativeAdapter
from evaluation.benchmark.adapters.opencode_openviking import OpenCodeOpenVikingAdapter
from evaluation.fixtures.raw_smoke import create_raw

ROOT=Path(__file__).resolve().parents[1]/"evaluation"
MODEL={"model":"provider/model","version":"fixed-v1","temperature":0,"max_output":256,"native_model_constraint":False}


def config():
    return {"model":MODEL,"hardware_class":"test-cpu","systems":{"data_explore":{
        "parser_version":"synthetic-table-parser/v1","smoke_parser":True,
        "parser_command":[sys.executable,"-m","evaluation.fixtures.smoke_parser"]}}}


def registry():
    return EntityRegistry(yaml.safe_load((ROOT/"cases/aliases.yaml").read_text())["entities"])


def test_frozen_raw_rejects_template_and_symlink_and_detects_mutation(tmp_path):
    raw=create_raw(tmp_path/"raw")
    frozen=freeze(raw,tmp_path/"frozen")
    verify(tmp_path/"frozen",frozen["fingerprint"])
    path=tmp_path/"frozen/models.docx"; path.chmod(0o644); path.write_bytes(b"changed")
    with pytest.raises(ValueError): verify(tmp_path/"frozen",frozen["fingerprint"])
    (raw/"tables.json").write_text("{}")
    with pytest.raises(ValueError): inventory(raw)
    (raw/"tables.json").unlink(); (raw/"alias.docx").symlink_to(raw/"models.docx")
    with pytest.raises(ValueError): inventory(raw)


def test_normalizer_is_system_independent_and_ambiguous_unknowns_reduce_precision():
    reg=registry()
    value={"metrics":["RSRP","Reference Signal Received Power"],"business_objects":["Cell"],"entities":["invented"]}
    norm=normalize(value,reg)
    assert norm.entities["metrics"]=={"metric:rsrp"}
    assert norm.entities["business_objects"]=={"business-object:cell"}
    assert normalize("Cell",reg).unknown  # two types, no fabricated identity
    result=score(norm,{"metrics":["metric:rsrp"]},optional=["business-object:cell"])
    assert result["recall"]==1 and result["precision"]==2/3
    assert result["f1"]==pytest.approx(.8)
    assert score(norm,{"metrics":["metric:rsrp"]},valid=False)["recall"]==0


def test_fields_are_qualified_from_returned_parent_not_gold():
    value={"primary_contexts":[{"path":"data://x","name":"LTE_PERIODIC_MR","type":"physical-model"}],
           "focused_expansion":{"data://x":{"fields":[{"column_name":"CELL_ID"}]}}}
    norm=normalize(value,registry())
    assert norm.entities["fields"]=={"field:lte-periodic-mr.cell-id"}


def test_usage_includes_parent_children_and_detects_missing_and_duplicate_records():
    parent={"call_id":"p","input_tokens":10,"output_tokens":3}
    child={"call_id":"c","input_tokens":20,"output_tokens":4}
    assert tokens([parent,child,parent],True)==(30,7,37)
    assert tokens([parent,{**parent,"input_tokens":100}],True)==(None,None,None)
    assert tokens([parent],False)==(None,None,None)
    assert tokens([],True)==(0,0,0)
    assert tool_counts([{"kind":"tool_call","call_id":"t","tool":"search"}]*2)["total"]==1


def test_opencode_export_counts_cache_reasoning_and_task_children():
    payload={"messages":[{"info":{"id":"m","role":"assistant","modelID":"model","providerID":"provider",
        "tokens":{"input":10,"output":2,"reasoning":3,"cache":{"read":4,"write":5}}},
        "parts":[{"id":"t","type":"tool","tool":"task","state":{"input":{"subagent_type":"explore"},"metadata":{"sessionID":"child"}}}]}]}
    calls,trace,children,complete=exported_calls(payload)
    assert complete and children==["child"] and tokens(calls,complete)==(19,5,24)
    payload["messages"][0]["info"]["tokens"].pop("input")
    assert exported_calls(payload)[3] is False


def test_native_wiki_requires_real_ingestion_receipt_and_never_gets_gold(tmp_path,monkeypatch):
    raw=create_raw(tmp_path/"raw"); work=tmp_path/"wiki"; work.mkdir()
    context=RunContext("run",1,str(work),fingerprint(inventory(raw)),MODEL,"test",True)
    received=[]
    def driver(command,payload,*args):
        received.append(payload)
        if payload["phase"]=="prepare":
            return {"status":"OK","consumed_files":inventory(raw),"stages":["llm_wiki_native_ingestion","wiki_index"],
                    "usage_complete":True,"llm_calls":[{"call_id":"ingest","input_tokens":100,"output_tokens":20}]}
        return {"status":"OK","raw_output":{"metrics":["RSRP"]},"usage_complete":True,
                "llm_calls":[{"call_id":"query","input_tokens":10,"output_tokens":2}],"tools_complete":True,"trace":[],"retrieval_rounds":1}
    monkeypatch.setattr("evaluation.benchmark.adapters.native_driver.invoke",driver)
    adapter=LLMWikiAdapter({"command":["native-wiki"]})
    assert adapter.prepare(str(raw),context).build_tokens_total==120
    assert adapter.query(BenchmarkCase("q","RSRP?"),QueryBudget(),context).query_tokens_total==12
    assert set(received[1]["case"])=={"case_id","query"}
    assert "aliases" not in str(received) and "gold" not in str(received)


def test_openviking_search_only_is_not_a_complete_agent_result(monkeypatch):
    monkeypatch.setattr(OpenCodeNativeAdapter,"query",lambda *a:QueryResult("opencode_openviking","q","OK",{"metrics":["RSRP"]},0,0,0))
    adapter=OpenCodeOpenVikingAdapter({}); adapter.target="viking://resources/test"
    result=adapter.query(BenchmarkCase("q","RSRP"),QueryBudget(),None)
    assert result.status=="INVALID"
    assert result.query_tokens_total is None


def test_actual_raw_parser_template_compiler_explore_smoke_and_reports(tmp_path):
    raw=create_raw(tmp_path/"raw"); out=tmp_path/"report"
    result=run(corpus_path=raw,cases_path=ROOT/"cases/cases.yaml",aliases_path=ROOT/"cases/aliases.yaml",
        config=config(),output=out,repeats=3,systems=["data_explore"],smoke=True,progress=None)
    assert not result["manifest"]["headline_eligible"]
    assert result["statistics"]["data_explore"]["invalid_run_rate"]==0
    details=[json.loads(line) for line in (out/"run_detail.jsonl").read_text().splitlines()]
    assert len(details)==18 and {r["category"] for r in details}=={"Q1","Q2","Q3","Q4","Q5","Q6"}
    assert all(r["result"]["query_tokens_total"]==0 for r in details)
    assert all(r["result"]["tool_calls"]==r["result"]["metadata"]["tool_counts"]["total"] for r in details)
    assert all("input" in event and "output" in event for r in details
               for event in r["result"]["trace"] if event["tool"].startswith("data_"))
    assert result["manifest"]["builds"]["data_explore"]["metadata"]["cold_build"]
    assert {"leaderboard.csv","category_breakdown.csv","source_span_breakdown.csv","amortized_cost.csv","statistics.json"} <= {p.name for p in out.iterdir()}
    amort=list(csv.DictReader((out/"amortized_cost.csv").open()))
    assert {int(r["N"]) for r in amort}=={1,10,100,1000}


def test_reused_snapshot_is_fingerprinted_and_never_reparses_or_accepts_tampering(tmp_path):
    raw=create_raw(tmp_path/"raw"); workspace=tmp_path/"work"; workspace.mkdir()
    cfg={**config()["systems"]["data_explore"],"cache_dir":str(tmp_path/"cache"),"reuse_snapshot":True}
    context=RunContext("r",0,str(workspace),fingerprint(inventory(raw)),MODEL,"test",True)
    first=DataExploreAdapter(cfg); cold=first.prepare(str(raw),context)
    second=DataExploreAdapter(cfg); warm=second.prepare(str(raw),context)
    assert cold.metadata["cold_build"] and warm.metadata["reused_snapshot"] and warm.build_tokens_total==0
    assert cold.metadata["snapshot_version"]==warm.metadata["snapshot_version"]
    target=next((tmp_path/"cache").rglob("quality.json")); target.write_text("[] ")
    with pytest.raises(ValueError,match="content changed"): DataExploreAdapter(cfg).prepare(str(raw),context)


def test_formal_contract_rejects_partial_system_set_and_smoke_parser(tmp_path):
    assert set(ADAPTERS)==set(SYSTEMS)
    with pytest.raises(ValueError,match="all four"):
        run(corpus_path="x",cases_path="x",aliases_path="x",config=config(),output=tmp_path/"out",repeats=1,systems=["data_explore"])
    with pytest.raises(ValueError,match="synthetic parser"):
        DataExploreAdapter(config()["systems"]["data_explore"]).prepare("x",RunContext("r",1,str(tmp_path),"f",MODEL,"test"))


def test_four_system_runner_keeps_identical_raw_and_private_scoring_inputs(tmp_path,monkeypatch):
    raw=create_raw(tmp_path/"raw")
    receipts=[]; queries=[]
    for system in SYSTEMS:
        class Probe:
            name=system
            def __init__(self,cfg): pass
            def prepare(self,corpus,context):
                receipts.append((self.name,corpus,inventory(corpus),context.corpus_fingerprint))
                assert sorted(p.name for p in Path(context.workspace).iterdir())==["raw"]
                assert set(asdict(context))=={"run_id","repeat","workspace","corpus_fingerprint","model","hardware_class","smoke"}
                return BuildResult(self.name,"OK",0,0,0)
            def query(self,case,budget,context):
                assert set(asdict(case))=={"case_id","query"}
                queries.append((self.name,asdict(case),asdict(budget)))
                return QueryResult(self.name,case.case_id,"OK",{"metrics":["RSRP"]},1,1,2,0,0)
            def cleanup(self): pass
        monkeypatch.setitem(ADAPTERS,system,Probe)
    result=run(corpus_path=raw,cases_path=ROOT/"cases/cases.yaml",aliases_path=ROOT/"cases/aliases.yaml",
        config=config(),output=tmp_path/"report",smoke=True,progress=None)
    assert len({r[1] for r in receipts})==4
    assert all(r[2:]==receipts[0][2:] for r in receipts)
    assert all([(q,b) for s,q,b in queries if s==system]==[(q,b) for s,q,b in queries if s==SYSTEMS[0]] for system in SYSTEMS)
    assert result["manifest"]["complete_four_system_run"]
    assert not result["manifest"]["headline_eligible"]  # mock contract tests never become a leaderboard
    assert result["manifest"]["query_budget"]["max_output_tokens"]==MODEL["max_output"]


def test_unavailable_system_is_retained_and_cost_remains_unknown(tmp_path):
    raw=create_raw(tmp_path/"raw")
    result=run(corpus_path=raw,cases_path=ROOT/"cases/cases.yaml",aliases_path=ROOT/"cases/aliases.yaml",
        config=config(),output=tmp_path/"report",systems=["llm_wiki"],smoke=True,progress=None)
    aggregate=result["statistics"]["llm_wiki"]
    assert aggregate["runs"]==18 and aggregate["invalid_run_rate"]==1
    assert aggregate["micro"]["recall"]==0
    assert aggregate["query_tokens_total"]["mean"] is None
    assert not result["manifest"]["token_usage_complete"]
    amort=list(csv.DictReader((tmp_path/"report/amortized_cost.csv").open()))
    assert all(r["AverageTokensPerQuery"]=="" for r in amort)


def test_micro_scoring_does_not_macro_average_different_gold_sizes():
    from evaluation.reports.e2e import micro,stats
    rows=[{"score":{"gold_count":1,"returned_count":1,"matched":["a"],"accepted_count":1}},
          {"score":{"gold_count":9,"returned_count":3,"matched":["b"],"accepted_count":1}}]
    assert micro(rows)=={"recall":.2,"precision":.5,"f1":pytest.approx(2/7)}
    assert stats([1,3,None])=={"mean":2,"std":1,"min":1,"max":3,"measured":2,"expected":3,"complete":False}


def test_opencode_recurses_children_but_requires_process_ledger_for_total_cost(tmp_path,monkeypatch):
    raw=create_raw(tmp_path/"raw"); workspace=tmp_path/"work"; workspace.mkdir()
    context=RunContext("run",1,str(workspace),fingerprint(inventory(raw)),MODEL,"test",True)
    calls=[]
    def message(mid,parts):
        return {"messages":[{"info":{"role":"assistant","id":mid,"tokens":{
            "input":10,"output":2,"reasoning":1,"cache":{"read":4,"write":0}}},"parts":parts}]}
    exports={"parent":message("p",[{"type":"tool","id":"task1","tool":"task","state":{
        "input":{"subagent_type":"explore"},"metadata":{"sessionID":"child"}}}]),
        "child":message("c",[{"type":"tool","id":"read1","tool":"read","state":{"input":{"filePath":"models.docx"}}}])}
    def execute(argv,**kwargs):
        calls.append(argv)
        if "--version" in argv: output="1.17.8"
        elif "export" in argv: output=json.dumps(exports[argv[-1]])
        else: output=json.dumps({"type":"text","sessionID":"parent","part":{"text":'{"metrics":["RSRP"]}'}})
        return SimpleNamespace(stdout=output,stderr="",returncode=0)
    monkeypatch.setattr("evaluation.benchmark.adapters.opencode_native.subprocess.run",execute)
    adapter=OpenCodeNativeAdapter({}); adapter.prepare(str(raw),context)
    first=adapter.query(BenchmarkCase("q","Find RSRP"),QueryBudget(),context)
    assert first.status=="OK" and first.tool_calls==2
    assert first.query_tokens_total is None and first.metadata["observed_session_tokens"]==(28,6,34)
    assert {c[-1] for c in calls if "export" in c}=={"parent","child"}
    def usage_driver(command,payload,*args):
        assert payload["session_ids"]==["child","parent"]
        return {"scope":"process_all_llm_calls","covered_session_ids":payload["session_ids"],"usage_complete":True,
            "llm_calls":[{"call_id":mid,"input_tokens":14,"output_tokens":3} for mid in ("p","c","background-summary")]}
    monkeypatch.setattr("evaluation.benchmark.adapters.opencode_native.invoke",usage_driver)
    adapter.config["usage_command"]=["provider-ledger"]
    second=adapter.query(BenchmarkCase("q","Find RSRP"),QueryBudget(),context)
    assert second.query_tokens_total==51 and second.metadata["usage_complete"]


def test_openviking_ingests_raw_bytes_and_rejects_queued_or_partial_receipts(tmp_path,monkeypatch):
    from evaluation.benchmark.adapters.opencode_openviking import validate_ingestion
    raw=create_raw(tmp_path/"raw"); workspace=tmp_path/"work"; workspace.mkdir()
    context=RunContext("run",0,str(workspace),fingerprint(inventory(raw)),MODEL,"test",True)
    monkeypatch.setattr("evaluation.benchmark.adapters.opencode_native.subprocess.run",
                        lambda *a,**kw:SimpleNamespace(stdout="1.17.8"))
    requests=[]
    def http(base,method,path,headers,timeout,**kw):
        requests.append((path,kw))
        if path.endswith("temp_upload"):
            assert any(p.read_bytes() in kw["raw_body"] for p in raw.iterdir())
            return {"status":"ok","result":{"temp_file_id":"upload"}}
        assert kw["body"]["wait"] and kw["body"]["processing_mode"]=="semantic_and_vectors"
        return {"status":"ok","result":{"status":"success","root_uri":kw["body"]["to"],"errors":[]},
                "telemetry":{"summary":{"tokens":{"llm":{"input":10,"output":2}}}}}
    monkeypatch.setattr("evaluation.benchmark.adapters.opencode_openviking.request_json",http)
    adapter=OpenCodeOpenVikingAdapter({"openviking":{"base_url":"http://fixture.invalid"}})
    build=adapter.prepare(str(raw),context)
    assert build.build_tokens_total==24 and len(requests)==4
    assert adapter.mcp["openviking"]["url"]=="http://fixture.invalid/mcp"
    for result in ({"status":"accepted"},{"status":"error"},
                   {"status":"success","root_uri":adapter.target,"meta":{"failed_files":["models.docx"]}},
                   {"status":"success","root_uri":adapter.target+"-another-run"}):
        with pytest.raises(ValueError): validate_ingestion({"status":"ok","result":result},adapter.target)
