"""Formal four-system raw-input benchmark. Legacy Evidence runs are separate."""
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import tempfile
import uuid
import yaml

from .result_contract import SYSTEMS, BenchmarkCase, BuildResult, QueryResult, QueryBudget, RunContext
from .raw_corpus import freeze, verify
from .adapters.llm_wiki import LLMWikiAdapter
from .adapters.opencode_native import OpenCodeNativeAdapter
from .adapters.opencode_openviking import OpenCodeOpenVikingAdapter
from .adapters.data_explore import DataExploreAdapter
from .entity_scoring import score
from evaluation.cases.schema import validate_cases
from evaluation.normalization.entity_registry import EntityRegistry
from evaluation.normalization.normalizer import normalize
from evaluation.reports.e2e import report

ADAPTERS={"llm_wiki":LLMWikiAdapter,"opencode_native":OpenCodeNativeAdapter,
          "opencode_openviking":OpenCodeOpenVikingAdapter,"data_explore":DataExploreAdapter}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(*,corpus_path,cases_path,aliases_path,config,output,repeats=3,systems=SYSTEMS,smoke=False,progress=print):
    if not systems or set(systems)-set(SYSTEMS) or len(systems)!=len(set(systems)):
        raise ValueError("only the four registered E2E systems are supported")
    if repeats<1 or not smoke and (repeats<3 or set(systems)!=set(SYSTEMS)):
        raise ValueError("formal benchmarks require all four systems and at least three repeats")
    model=config.get("model",{})
    if not all(k in model for k in ("model","version","temperature","max_output","native_model_constraint")) or not config.get("hardware_class"):
        raise ValueError("explicit model/version/temperature/output/constraint and hardware settings required")
    output=Path(output).resolve()
    output.mkdir(parents=True,exist_ok=True)
    if any(output.iterdir()): raise ValueError("output must be empty; never mix different benchmark runs")
    registry=EntityRegistry(yaml.safe_load(Path(aliases_path).read_text())["entities"])
    rows=yaml.safe_load(Path(cases_path).read_text())["cases"]
    details=[]; builds={}; run_id=uuid.uuid4().hex
    budget=QueryBudget(**{**config.get("query_budget",{}),"max_output_tokens":model["max_output"]})
    if any(not isinstance(v,int) or isinstance(v,bool) or v<=0 for v in asdict(budget).values()):
        raise ValueError("query budgets must be positive integers")
    manifest={"format":"raw-e2e/v1","run_id":run_id,"created_at":datetime.now(timezone.utc).isoformat(),
        "smoke":smoke,"systems":list(systems),"repeats":repeats,"model":model,"hardware_class":config["hardware_class"],
        "cases_sha256":digest(cases_path),"aliases_sha256":digest(aliases_path),"builds":builds,
        "query_budget":asdict(budget),
        "configuration_sha256":hashlib.sha256(json.dumps(config,sort_keys=True).encode()).hexdigest(),
        "cost_scope":"all reported LLM calls, cached input and reasoning included; unknown usage is null",
        "normalizer_version":"canonical-entities/v1","scorer_version":"entity-recall-precision/v1"}
    with tempfile.TemporaryDirectory(prefix="raw-e2e-") as temp:
        root=Path(temp)
        frozen=freeze(corpus_path,root/"frozen")
        manifest["raw_corpus"]=frozen
        validate_cases(rows,registry,{r["path"] for r in frozen["files"]},smoke)
        # This directory contains only private native inputs/builds, never cases or aliases.
        for system in systems:
            workspace=root/system; workspace.mkdir()
            private=freeze(root/"frozen",workspace/"raw")
            assert private==frozen
            context=RunContext(run_id,0,str(workspace),frozen["fingerprint"],model,config["hardware_class"],smoke)
            adapter=ADAPTERS[system](config.get("systems",{}).get(system,{}))
            try:
                try:
                    build=adapter.prepare(str(workspace/"raw"),context)
                    verify(workspace/"raw",frozen["fingerprint"])
                    if build.system!=system: raise ValueError("build system mismatch")
                except Exception as exc:
                    build=BuildResult(system,"UNAVAILABLE",metadata={"error":type(exc).__name__+": "+str(exc)})
                builds[system]=asdict(build)
                for row in rows:
                    for repeat in range(1,repeats+1):
                        query_context=RunContext(run_id,repeat,str(workspace),frozen["fingerprint"],model,config["hardware_class"],smoke)
                        if build.status!="OK":
                            result=QueryResult(system,row["case_id"],"UNAVAILABLE",metadata={"build_error":build.metadata.get("error")})
                        else:
                            try:
                                verify(workspace/"raw",frozen["fingerprint"])
                                result=adapter.query(BenchmarkCase(row["case_id"],row["query"]),budget,query_context)
                                verify(workspace/"raw",frozen["fingerprint"])
                                if result.system!=system or result.case_id!=row["case_id"]:
                                    raise ValueError("query result identity mismatch")
                            except Exception as exc:
                                result=QueryResult(system,row["case_id"],"INVALID",metadata={"error":type(exc).__name__+": "+str(exc)})
                        normalized=normalize(result.raw_output,registry)
                        scored=score(normalized,row["gold"],row.get("optional"),row.get("forbidden"),result.status=="OK")
                        detail={"system":system,"case_id":row["case_id"],"query":row["query"],"repeat":repeat,
                            "category":row["category"],"source_span":row["difficulty"]["source_span"],
                            "result":asdict(result),"normalized":normalized.to_dict(),"score":scored}
                        details.append(detail)
                        with (output/"run_detail.jsonl").open("a") as handle: handle.write(json.dumps(detail,ensure_ascii=False)+"\n")
                        if progress: progress(f"{system} {row['case_id']} {repeat}/{repeats}: {result.status}")
            finally:
                try: adapter.cleanup()
                except Exception as exc: manifest.setdefault("cleanup_errors",[]).append({"system":system,"error":type(exc).__name__})
            (output/"run_manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
        verify(root/"frozen",frozen["fingerprint"])
    aggregate=report(output,details,builds)
    manifest["complete_four_system_run"]=set(systems)==set(SYSTEMS) and all(b["status"]=="OK" for b in builds.values()) and all(r["result"]["status"]=="OK" for r in details)
    manifest["token_usage_complete"]=all(b["build_tokens_total"] is not None for b in builds.values()) and all(r["result"]["query_tokens_total"] is not None for r in details)
    manifest["tool_usage_complete"]=all(r["result"]["tool_calls"] is not None and r["result"]["retrieval_rounds"] is not None for r in details)
    manifest["headline_eligible"]=not smoke and manifest["complete_four_system_run"] and manifest["token_usage_complete"] and manifest["tool_usage_complete"]
    (output/"run_manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
    return {"manifest":manifest,"statistics":aggregate}
