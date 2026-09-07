"""Only official runner: frozen raw inputs, fail-fast preflight, independent scoring."""
from dataclasses import asdict
from contextlib import nullcontext
from pathlib import Path
import json
import tempfile
import time
import uuid
import yaml

from .result_contract import SYSTEMS, BenchmarkCase, BuildResult, QueryResult, QueryBudget, RunContext
from .raw_corpus import freeze, verify
from .adapters.llm_wiki import LLMWikiAdapter
from .adapters.opencode_native import OpenCodeNativeAdapter
from .adapters.opencode_openviking import OpenCodeOpenVikingAdapter
from .adapters.data_explore import DataExploreAdapter
from .entity_scoring import score
from .output_contract import empty_output, set_output
from .usage import nonnegative, coherent_usage
from .preflight import (PreflightError, static_checks, isolation_probe, guard_workspace,
                        validate_probe, PROBE_CASE, check, verify_model)
from .run_manifest import manifest as make_manifest, model_profile
from evaluation.cases.schema import validate_cases, distribution
from evaluation.normalization.entity_registry import EntityRegistry
from evaluation.normalization.normalizer import normalize
from evaluation.reports.e2e import report

ADAPTERS={"llm_wiki":LLMWikiAdapter,"opencode_native":OpenCodeNativeAdapter,
          "opencode_openviking":OpenCodeOpenVikingAdapter,"data_explore":DataExploreAdapter}


def run(*,corpus_path,cases_path,aliases_path,config,output,repeats=3,systems=SYSTEMS,
        smoke=False,progress=print,preflight_only=False):
    if not systems or set(systems)-set(SYSTEMS) or len(systems)!=len(set(systems)):
        raise ValueError("only the four registered E2E systems are supported")
    if repeats<1 or not smoke and (repeats<3 or set(systems)!=set(SYSTEMS)):
        raise ValueError("formal benchmarks require all four systems and at least three repeats")
    model=config.get("model",{})
    if not all(k in model for k in ("model","version","temperature","max_output","native_model_constraint")) or not config.get("hardware_class"):
        raise ValueError("explicit model/version/temperature/output/constraint and hardware settings required")
    if "context_tokens" in config.get("query_budget",{}):
        raise ValueError("rename context_tokens to native_context_budget; it is not a shared hard limit")
    budget=QueryBudget(**{**config.get("query_budget",{}),"max_output_tokens":model["max_output"]})
    if any(not isinstance(v,int) or isinstance(v,bool) or v<=0 for v in asdict(budget).values()):
        raise ValueError("query budgets must be positive integers")
    output=Path(output).resolve()
    output.mkdir(parents=True,exist_ok=True)
    if any(output.iterdir()): raise ValueError("output must be empty; never mix different benchmark runs")
    registry=EntityRegistry(yaml.safe_load(Path(aliases_path).read_text())["entities"])
    rows=yaml.safe_load(Path(cases_path).read_text())["cases"]
    run_id=uuid.uuid4().hex
    manifest=make_manifest(config,run_id,systems,ADAPTERS,cases_path,aliases_path,smoke,repeats,asdict(budget))
    details=[]; active={}; builds=manifest["builds"]; protected=(cases_path,aliases_path)
    checks=manifest["preflight"]["checks"]

    def checkpoint():
        (output/"run_manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2))

    def invoke_query(adapter,case,context):
        started=time.monotonic()
        try:
            guard_workspace(context.workspace,protected)
            try: verify(Path(context.workspace)/"raw",context.corpus_fingerprint)
            except ValueError as exc: raise PreflightError(str(exc)) from exc
            result=adapter.query(case,budget,context)
            guard_workspace(context.workspace,protected)
            try: verify(Path(context.workspace)/"raw",context.corpus_fingerprint)
            except ValueError as exc: raise PreflightError(str(exc)) from exc
            if result.system!=adapter.name or result.case_id!=case.case_id:
                raise ValueError("query result identity mismatch")
            set_output(result,result.output if result.output is not None else result.raw_output)
            if result.query_llm_total_tokens is not None and not coherent_usage(result,"query"):
                result.query_llm_input_tokens=result.query_llm_output_tokens=result.query_llm_total_tokens=None
                result.metadata["usage_error"]="inconsistent query LLM cost contract"
            if not nonnegative(result.delivered_context_tokens): result.delivered_context_tokens=None
            if result.delivered_context_tokens is None:
                result.metadata.setdefault("delivered_context_measurement",{}).setdefault("reason","native adapter cannot isolate delivered context reliably")
            return result
        except PreflightError:
            raise
        except Exception as exc:
            return QueryResult(adapter.name,case.case_id,"INVALID",latency_ms=int(1000*(time.monotonic()-started)),
                               metadata={"error":type(exc).__name__+": "+str(exc),
                                         "delivered_context_measurement":{"reason":"query failed before a reliable context measurement"}})

    temporary=tempfile.TemporaryDirectory(prefix="raw-e2e-")
    try:
        with nullcontext(temporary.name) as temp:
            root=Path(temp); frozen=freeze(corpus_path,root/"frozen")
            manifest.update(raw_corpus=frozen,corpus_hash=frozen["fingerprint"])
            validate_cases(rows,registry,{r["path"] for r in frozen["files"]},smoke)
            manifest["dataset_distribution"]=distribution(rows)
            if not smoke:
                check(checks,"raw_office_inputs",all(Path(r["path"]).suffix.lower() in {".doc",".docx",".xls",".xlsx"} for r in frozen["files"]),
                      "formal Pilot external inputs are frozen original Word/Excel files")
                static_checks(config,systems,checks)
            # Every native build/probe passes before any scored query is dispatched.
            for system in systems:
                workspace=root/system; workspace.mkdir()
                private=freeze(root/"frozen",workspace/"raw")
                if private!=frozen: raise PreflightError("raw corpus fingerprint mismatch")
                guard_workspace(workspace,protected)
                if not smoke:
                    check(checks,"raw_fingerprint",private==frozen,"byte-identical raw corpus",system)
                    isolation_probe(config,workspace,checks)
                cfg=dict(config.get("systems",{}).get(system,{}))
                if config.get("isolation_command"): cfg["execution_prefix"]=config["isolation_command"]
                adapter=ADAPTERS[system](cfg); active[system]=adapter
                context=RunContext(run_id,0,str(workspace),frozen["fingerprint"],model,config["hardware_class"],smoke)
                try:
                    build=adapter.prepare(str(workspace/"raw"),context)
                    verify(workspace/"raw",frozen["fingerprint"])
                    guard_workspace(workspace,protected)
                    if build.system!=system: raise ValueError("build system mismatch")
                except Exception as exc:
                    if isinstance(exc,PreflightError): raise
                    build=BuildResult(system,"UNAVAILABLE",metadata={"error":type(exc).__name__+": "+str(exc)})
                builds[system]=asdict(build)
                manifest["system_profiles"][system]["build"]={
                    "cold_or_cached":"cached" if build.metadata.get("reused_snapshot") is True else (
                        "cold" if build.metadata.get("cold_build") is True else "unknown"),
                    "snapshot_version":build.metadata.get("snapshot_version"),
                    "native_version":build.metadata.get("native_version",build.metadata.get("version")),
                    "parser_version":build.metadata.get("parser_version"),
                    "compiler_version":build.metadata.get("compiler_version"),
                    "declared_build_model":build.metadata.get("effective_model"),
                    "openviking_model":build.metadata.get("openviking_model")}
                if not smoke:
                    check(checks,"adapter_available",build.status=="OK",str(build.metadata.get("error") or "native build ready"),system)
                    probe=invoke_query(adapter,PROBE_CASE,context)
                    manifest["preflight"]["probes"][system]=asdict(probe)
                    checkpoint()
                    validate_probe(system,build,probe,model,checks)
                checkpoint()
            if not smoke: manifest["preflight"]["status"]="PASS"
            manifest["preflight"]["query_llm_total_tokens"]=sum(p["query_llm_total_tokens"] for p in manifest["preflight"]["probes"].values()) if all(
                p["query_llm_total_tokens"] is not None for p in manifest["preflight"]["probes"].values()) else None
            if not preflight_only:
                for system,adapter in active.items():
                    context_workspace=str(root/system)
                    for row in rows:
                        for repeat in range(1,repeats+1):
                            context=RunContext(run_id,repeat,context_workspace,frozen["fingerprint"],model,config["hardware_class"],smoke)
                            if builds[system]["status"]!="OK":
                                result=QueryResult(system,row["case_id"],"UNAVAILABLE",metadata={"build_error":builds[system]["metadata"].get("error")})
                            else:
                                result=invoke_query(adapter,BenchmarkCase(row["case_id"],row["query"]),context)
                            normalized=normalize(result.output or empty_output(),registry)
                            scored=score(normalized,row["gold"],row.get("optional"),row.get("forbidden"),
                                         result.status=="OK",row["expected_empty"],row.get("relations"))
                            detail={"system":system,"case_id":row["case_id"],"query":row["query"],"repeat":repeat,
                                    "repeat_index":repeat,"category":row["category"],"source_span":row["source_span"],
                                    "difficulty":row["difficulty"],"tags":row["tags"],"result":asdict(result),
                                    "effective_model":model_profile(result.metadata.get("effective_model") or {}),
                                    "normalized":normalized.to_dict(),"score":scored}
                            details.append(detail)
                            with (output/"run_detail.jsonl").open("a") as handle:
                                handle.write(json.dumps(detail,ensure_ascii=False)+"\n")
                            if progress: progress(f"{system} {row['case_id']} {repeat}/{repeats}: {result.status}")
                    checkpoint()
            verify(root/"frozen",frozen["fingerprint"])
            for system in active:
                guard_workspace(root/system,protected)
    except Exception as exc:
        manifest["preflight"]["status"]="FAIL" if not details else "RUN_FAILED"
        manifest["failure"]={"type":type(exc).__name__,"message":str(exc)}
        checkpoint()
        raise
    finally:
        for system,adapter in active.items():
            try: adapter.cleanup()
            except Exception as exc: manifest.setdefault("cleanup_errors",[]).append({"system":system,"error":type(exc).__name__})
        temporary.cleanup()
        checkpoint()
    aggregate=report(output,details,builds) if details else {}
    manifest["complete_four_system_run"]=bool(details) and set(systems)==set(SYSTEMS) and all(b["status"]=="OK" for b in builds.values()) and all(r["result"]["status"]=="OK" for r in details)
    manifest["token_usage_complete"]=all(b["build_llm_total_tokens"] is not None for b in builds.values()) and all(r["result"]["query_llm_total_tokens"] is not None for r in details)
    manifest["tool_usage_complete"]=all(r["result"]["tool_calls"] is not None and r["result"]["retrieval_rounds"] is not None for r in details)
    manifest["model_usage_complete"]=all(r["result"]["metadata"].get("model_settings_verified") is True
        and verify_model(r["result"]["metadata"].get("effective_model"),model) for r in details)
    manifest["headline_eligible"]=not smoke and manifest["preflight"]["status"]=="PASS" and manifest["complete_four_system_run"] and manifest["token_usage_complete"] and manifest["tool_usage_complete"] and manifest["model_usage_complete"]
    checkpoint()
    return {"manifest":manifest,"statistics":aggregate}
