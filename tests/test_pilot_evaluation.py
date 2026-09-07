"""Contract/regression tests only; simulated adapters never represent Pilot results."""
from copy import deepcopy
import csv
import json
from pathlib import Path
import shutil
import sys
import yaml
import pytest

from evaluation.benchmark.result_contract import BuildResult, QueryResult, SYSTEMS, CATEGORIES, QueryBudget
from evaluation.benchmark.output_contract import empty_output, descriptor, validate_output, bundle_output
from evaluation.benchmark.entity_scoring import score
from evaluation.normalization.normalizer import normalize
from evaluation.normalization.entity_registry import EntityRegistry
from evaluation.cases.schema import validate_cases, distribution
from evaluation.benchmark.preflight import (PreflightError, guard_workspace, validate_probe, verify_model,
                                           static_checks, isolation_probe, PROBE_CASE)
from evaluation.benchmark.e2e_runner import run, ADAPTERS
from evaluation.fixtures.raw_smoke import create_raw
from evaluation.reports.e2e import report

ROOT=Path(__file__).resolve().parents[1]/"evaluation"
MODEL={"model":"fixture/model","version":"pinned","temperature":0,"max_output":256,"native_model_constraint":False}


def registry():
    return EntityRegistry(yaml.safe_load((ROOT/"cases/aliases.yaml").read_text())["entities"])


def cases():
    return yaml.safe_load((ROOT/"cases/cases.yaml").read_text())["cases"]


def negative_case():
    return {"case_id":"negative-fixture","category":"negative","source_span":"cross_document",
            "difficulty":"hard","tags":["synthetic"],"review_status":"FIXTURE","expected_empty":True,
            "query":"材料是否定义了 VoNR 掉话分析模型？","gold":{},"relations":[],
            "source_documents":["models.docx","dictionary.xlsx"],
            "cross_document_rationale":"Check the model inventory and field dictionary together.",
            "empty_rationale":"The complete synthetic fixture contains only two LTE tables; it cannot establish a VoNR model."}


def test_public_output_contract_contains_no_answers_and_rejects_loose_formats():
    output=empty_output()
    assert validate_output(json.dumps(output))==output
    assert set(descriptor()["entity_types"])==set(output)-{"schema","relations"}
    assert "RSRP" not in json.dumps(descriptor()) and "gold" not in json.dumps(descriptor()).lower()
    for bad in ({},"RSRP",{**output,"metrics":"RSRP"},{**output,"schema":"v0"},
                {**output,"gold":["metric:rsrp"]},{**output,"metrics":[42]}):
        with pytest.raises((ValueError,TypeError)): validate_output(bad)
    output["relations"]=[{"source":{"type":"metrics","name":"RSRP"},"relation":"supported_by",
                          "target":{"type":"physical_models","name":"LTE_PERIODIC_MR"}}]
    with pytest.raises(ValueError,match="endpoints"): validate_output(output)
    output.update(metrics=["RSRP"],physical_models=["LTE_PERIODIC_MR"])
    assert validate_output(output)==output


def test_bundle_formatter_preserves_delivered_fields_and_supported_relations_only():
    bundle={"primary_contexts":[{"path":"p","type":"physical-model","name":"LTE_PERIODIC_MR"}],
            "focused_expansion":{"p":{"metrics":["RSRP"],"fields":[{"column_name":"CELL_ID"}],
                "candidates":{"metrics":["invented"]}}},
            "candidates":[{"name":"invented"}],"environment":{"matched_assets":[]}}
    output=bundle_output(bundle)
    assert output["fields"]==["LTE_PERIODIC_MR.CELL_ID"] and "invented" not in json.dumps(output)
    edge=output["relations"][0]
    assert edge["source"]["name"]=="RSRP" and edge["target"]["name"]=="LTE_PERIODIC_MR"
    assert edge["relation"]=="supported_by"
    # Co-returned logical and physical names do not imply implementation/identity.
    bundle["primary_contexts"].append({"path":"l","type":"logical-model","name":"LTE_PERIODIC_MR"})
    assert len(bundle_output(bundle)["relations"])==1


def test_negative_empty_correct_unknown_false_positive_and_invalid_not_success():
    reg=registry()
    success=score(normalize(empty_output(),reg),{},expected_empty=True,relations=[])
    assert success["negative_correct"] and not success["negative_false_positive"]
    assert success["recall"] is None and success["f1"] is None
    output={**empty_output(),"physical_models":["invented VoNR model"]}
    wrong=score(normalize(output,reg),{},expected_empty=True,relations=[])
    assert not wrong["negative_correct"] and wrong["negative_false_positive"] and wrong["precision"]==0
    assert not score(normalize(empty_output(),reg),{},valid=False,expected_empty=True)["negative_correct"]


def test_relation_direction_and_aliases_are_scored_separately_from_entity_f1():
    output={**empty_output(),"metrics":["Reference Signal Received Power"],"physical_models":["LTE_PERIODIC_MR"]}
    correct={"source":{"type":"metrics","name":output["metrics"][0]},"relation":"supported_by",
             "target":{"type":"physical_models","name":"LTE_PERIODIC_MR"}}
    output["relations"]=[correct,correct]  # canonical dedup
    gold={"metrics":["metric:rsrp"],"physical_models":["physical-model:lte-periodic-mr"]}
    relations=[{"source":"metric:rsrp","relation":"supported_by","target":"physical-model:lte-periodic-mr"}]
    scored=score(normalize(validate_output(output),registry()),gold,relations=relations)
    assert scored["f1"]==1 and scored["relation"]["f1"]==1
    output["relations"]=[{**correct,"source":correct["target"],"target":correct["source"]}]
    reversed_score=score(normalize(output,registry()),gold,relations=relations)
    assert reversed_score["f1"]==1 and reversed_score["relation"]["f1"]==0
    assert score(normalize(output,registry()),gold)["relation"]["f1"] is None


def test_pilot_schema_negative_evidence_and_quota_warnings_are_not_hard_gates():
    rows=[r for r in cases() if r["category"]!="negative"]+[negative_case()]
    assert validate_cases(rows,registry(),{"models.docx","dictionary.xlsx"},smoke=True)==rows
    dist=distribution(rows)
    assert sum(dist["recommended_targets"].values())==60 and dist["total"]==7
    assert dist["warnings"] and dist["categories"]["negative"]==1
    broken=deepcopy(rows); broken[-1].pop("empty_rationale")
    with pytest.raises(ValueError,match="rationale"): validate_cases(broken,registry(),{"models.docx","dictionary.xlsx"},True)
    broken=deepcopy(rows); broken[-1]["gold"]={"metrics":["metric:rsrp"]}
    with pytest.raises(ValueError,match="negative"): validate_cases(broken,registry(),{"models.docx","dictionary.xlsx"},True)
    with pytest.raises(ValueError,match="approved"): validate_cases(rows,registry(),{"models.docx","dictionary.xlsx"})


def test_leakage_guard_blocks_renamed_file_embedded_alias_and_symlink(tmp_path):
    work=tmp_path/"workspace"; work.mkdir()
    protected=[ROOT/"cases/cases.yaml",ROOT/"cases/aliases.yaml"]
    guard_workspace(work,protected)
    copied=work/"innocent.txt"; shutil.copyfile(protected[1],copied)
    with pytest.raises(PreflightError,match="copied"): guard_workspace(work,protected)
    copied.unlink()
    (work/"cache.json").write_text(json.dumps({"cache":yaml.safe_load(protected[1].read_text())["entities"][0]}))
    with pytest.raises(PreflightError,match="leaked"): guard_workspace(work,protected)
    (work/"cache.json").unlink(); (work/"link").symlink_to(protected[0])
    with pytest.raises(PreflightError,match="symbolic"): guard_workspace(work,protected)


def test_preflight_rejects_unknown_telemetry_or_unverified_model():
    result=QueryResult("data_explore",PROBE_CASE.case_id,"OK",output=empty_output(),
        query_llm_input_tokens=0,query_llm_output_tokens=0,query_llm_total_tokens=0,tool_calls=2,retrieval_rounds=2,
        metadata={"effective_model":MODEL,"model_settings_verified":True})
    build=BuildResult("data_explore","OK",0,0,0)
    checks=[]; validate_probe("data_explore",build,result,MODEL,checks)
    assert all(c["status"]=="PASS" for c in checks)
    result.query_llm_total_tokens=None
    with pytest.raises(PreflightError,match="query_telemetry"): validate_probe("data_explore",build,result,MODEL,[])
    result.query_llm_total_tokens=0; result.metadata["model_settings_verified"]=False
    with pytest.raises(PreflightError,match="effective_model"): validate_probe("data_explore",build,result,MODEL,[])
    assert not verify_model({**MODEL,"temperature":.9},MODEL)
    assert verify_model({**MODEL,"temperature":.9,"native_model_constraint":True,"reason":"native fixed temperature"},MODEL)


def test_isolation_probe_detects_a_passthrough_launcher(tmp_path):
    work=tmp_path/"work"; work.mkdir()
    launcher=tmp_path/"unsafe_launcher.py"
    launcher.write_text("import subprocess,sys\nsys.exit(subprocess.call(sys.argv[sys.argv.index('--')+1:]))\n")
    with pytest.raises(PreflightError,match="workspace_confinement"):
        isolation_probe({"isolation_command":[sys.executable,str(launcher)]},work,[])


def test_preflight_fails_before_any_case_and_writes_a_failure_manifest(tmp_path,monkeypatch):
    raw=create_raw(tmp_path/"raw")
    approved=cases()
    for row in approved: row["review_status"]="APPROVED"  # unit-test-only copy
    case_path=tmp_path/"cases.yaml"; case_path.write_text(yaml.safe_dump({"cases":approved}))
    class ShouldNotRun:
        def __init__(self,*args): raise AssertionError("no native calls before static preflight")
    for system in SYSTEMS: monkeypatch.setitem(ADAPTERS,system,ShouldNotRun)
    out=tmp_path/"report"
    with pytest.raises(PreflightError,match="isolation_launcher"):
        run(corpus_path=raw,cases_path=case_path,aliases_path=ROOT/"cases/aliases.yaml",
            config={"model":MODEL,"hardware_class":"fixture"},output=out,progress=None)
    manifest=json.loads((out/"run_manifest.json").read_text())
    assert manifest["preflight"]["status"]=="FAIL" and not manifest["headline_eligible"]
    assert not (out/"run_detail.jsonl").exists()


def test_repeated_reports_negative_relation_cross_document_and_amortization(tmp_path):
    reg=registry(); rows=[]
    positive={**empty_output(),"metrics":["RSRP"]}
    for repeat in (1,2,3):
        for cid,output,gold,span,isnegative in (
            ("positive",positive,{"metrics":["metric:rsrp"]},"cross_document",False),
            ("negative",empty_output() if repeat<3 else positive,{},"single_document",True)):
            result=QueryResult("fixture",cid,"OK",output,repeat*10,0,repeat*10,2,1,
                               delivered_context_tokens=5 if repeat<3 else None)
            rows.append({"system":"fixture","case_id":cid,"repeat":repeat,"category":"negative" if isnegative else "metric_to_model",
                         "source_span":span,"result":__import__('dataclasses').asdict(result),
                         "score":score(normalize(output,reg),gold,expected_empty=isnegative,relations=[])})
    builds={"fixture":__import__('dataclasses').asdict(BuildResult("fixture","OK",90,10,100,metadata={"reused_snapshot":False}))}
    aggregates=report(tmp_path,rows,builds); aggregate=aggregates["fixture"]
    assert aggregate["negative_case_accuracy"]==pytest.approx(2/3)
    assert aggregate["false_positive_rate"]==pytest.approx(1/3)
    assert aggregate["micro"]["recall"]==1 and aggregate["micro"]["precision"]==.75
    assert aggregate["repeat_statistics"]["precision"]["std"]>0
    head=list(csv.DictReader((tmp_path/"leaderboard.csv").open()))[0]
    assert head["AvgQueryLLMTokens"]=="20" and head["AvgDeliveredContextTokens"]==""
    assert "AvgQueryTokens" not in head and head["CrossDocumentRecall"]=="1.0"
    amort=list(csv.DictReader((tmp_path/"amortized_cost.csv").open()))
    assert [float(r["AverageLLMTokensPerQuery"]) for r in amort]==[120,30,21,20.1]
    assert (tmp_path/"effect_cost_scatter.csv").exists()
    assert {r["SourceSpan"] for r in csv.DictReader((tmp_path/"source_span_breakdown.csv").open())}=={"single_document","cross_document"}


def test_native_budget_name_and_cost_fields_are_unambiguous():
    from dataclasses import asdict
    assert "native_context_budget" in asdict(QueryBudget()) and "context_tokens" not in asdict(QueryBudget())
    result=asdict(QueryResult("fixture","q","OK"))
    assert result["query_llm_total_tokens"] is None and result["delivered_context_tokens"] is None
    assert "query_tokens_total" not in result


def test_all_native_probes_precede_scored_queries_and_cleanup_has_workspace(tmp_path,monkeypatch):
    raw=create_raw(tmp_path/"raw"); approved=cases()
    for row in approved: row["review_status"]="APPROVED"  # synthetic unit-test copy, never a published dataset
    case_path=tmp_path/"cases.yaml"; case_path.write_text(yaml.safe_dump({"cases":approved}))
    events=[]
    monkeypatch.setattr("evaluation.benchmark.e2e_runner.static_checks",lambda *a:None)
    monkeypatch.setattr("evaluation.benchmark.e2e_runner.isolation_probe",lambda *a:None)
    for system in SYSTEMS:
        class SimulatedNative:
            name=system
            def __init__(self,config): pass
            def prepare(self,corpus,context):
                self.workspace=context.workspace; events.append(("build",self.name))
                return BuildResult(self.name,"OK",0,0,0,metadata={"target_uri":"viking://resources/test","cold_build":True})
            def query(self,case,budget,context):
                events.append((case.case_id,self.name))
                trace=[{"tool":"task","native":{"state":{"input":{"subagent_type":"explore"}}}},
                       {"tool":"openviking_search","native":{"state":{"input":{"target_uri":"viking://resources/test"}}}}]
                return QueryResult(self.name,case.case_id,"OK",empty_output(),0,0,0,2,1,trace=trace,
                    metadata={"effective_model":MODEL,"model_settings_verified":True})
            def cleanup(self): assert Path(self.workspace).exists()
        monkeypatch.setitem(ADAPTERS,system,SimulatedNative)
    out=tmp_path/"simulated-contract-test"
    result=run(corpus_path=raw,cases_path=case_path,aliases_path=ROOT/"cases/aliases.yaml",
        config={"model":MODEL,"hardware_class":"unit-test"},output=out,progress=None)
    assert all(cid in {"build",PROBE_CASE.case_id} for cid,_ in events[:8])
    assert {system for cid,system in events[:8] if cid==PROBE_CASE.case_id}==set(SYSTEMS)
    assert len((out/"run_detail.jsonl").read_text().splitlines())==len(approved)*4*3
    manifest=result["manifest"]
    assert manifest["preflight"]["status"]=="PASS" and len(manifest["preflight"]["probes"])==4
    assert manifest["git_commit"] and manifest["corpus_hash"] and manifest["case_set_hash"]
    assert manifest["environment"]["python_version"] and manifest["system_profiles"]["llm_wiki"]["adapter_version"]
    assert manifest["preflight"]["query_llm_total_tokens"]==0
