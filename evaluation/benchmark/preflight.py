"""Fail-fast engineering checks. Probes have no Gold, aliases or benchmark answers."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from .result_contract import SYSTEMS, BenchmarkCase
from .output_contract import validate_output
from .usage import nonnegative, coherent_usage
from .adapters.native_driver import isolated_command


class PreflightError(ValueError):
    pass


def check(checks, code, passed, detail, system=None):
    checks.append({"code":code,"status":"PASS" if passed else "FAIL","severity":"P0",
                   "system":system,"detail":detail})
    if not passed: raise PreflightError(f"{code}: {detail}")


def executable(command):
    argv=[command] if isinstance(command,str) else command
    return bool(isinstance(argv,list) and argv and all(isinstance(s,str) for s in argv) and shutil.which(argv[0]))


def static_checks(config, systems, checks):
    check(checks,"four_adapters",set(systems)==set(SYSTEMS),"formal Pilot requires exactly four systems")
    model=config.get("model",{})
    check(checks,"model_profile",bool(model.get("model") and model.get("version")
        and isinstance(model.get("temperature"),(int,float)) and not isinstance(model.get("temperature"),bool)
        and nonnegative(model.get("max_output")) and model["max_output"]>0
        and isinstance(model.get("native_model_constraint"),bool)),"pin backbone/version/temperature/max_output")
    check(checks,"isolation_launcher",executable(config.get("isolation_command")),
          "configure an executable native-process isolation launcher")
    for system in systems:
        cfg=config.get("systems",{}).get(system,{})
        if system=="data_explore":
            command=cfg.get("parser_command")
            check(checks,"production_parser",not cfg.get("smoke_parser") and "smoke_parser" not in str(command)
                  and cfg.get("parser_version") and "synthetic" not in cfg["parser_version"],
                  "formal Domain Parser is required; fixture parser is forbidden",system)
            check(checks,"parser_executable",executable(command),"Domain Parser command available",system)
        else:
            check(checks,"adapter_executable",executable(cfg.get("command","opencode" if system.startswith("opencode") else None)),
                  "native command available",system)
        if system.startswith("opencode"):
            check(checks,"process_telemetry",executable(cfg.get("usage_command")),"process-wide LLM ledger collector required",system)
        if system=="opencode_openviking":
            ov=cfg.get("openviking",{})
            check(checks,"openviking_configuration",bool(ov.get("base_url") and ov.get("version") and ov.get("model")),
                  "pin OpenViking service/version/ingestion model",system)


def isolation_probe(config, workspace, checks):
    """Test launcher confinement using a disposable sibling canary, never a Gold file."""
    canary=Path(workspace).parent/"scorer-access-canary"
    canary.write_text("preflight-only; contains no benchmark information")
    script="import pathlib,sys\ntry:\n pathlib.Path(sys.argv[1]).read_bytes()\nexcept (PermissionError,FileNotFoundError):\n sys.exit(0)\nexcept OSError:\n sys.exit(2)\nelse:\n sys.exit(1)"
    try:
        result=subprocess.run(isolated_command([sys.executable,"-c",script,str(canary)],str(workspace),
            config.get("isolation_command")),capture_output=True,text=True,timeout=30)
        check(checks,"workspace_confinement",result.returncode==0,
              "same native launcher must deny reading a sibling scorer canary",Path(workspace).name)
    finally:
        canary.unlink(missing_ok=True)


def guard_workspace(workspace, protected_paths):
    """Scorer-side scan of full-file copies and embedded JSON/YAML records, plus links."""
    import yaml
    forbidden=[]; protected=[]
    for path in protected_paths:
        payload=Path(path).read_bytes(); protected.append(Path(path).resolve())
        parsed=yaml.safe_load(payload)
        forbidden.extend(parsed.get("cases",parsed.get("entities",[])))
    hashes={hashlib.sha256(p.read_bytes()).hexdigest() for p in protected}
    def embedded(value):
        if any(value==record for record in forbidden): return True
        if isinstance(value,dict): return any(embedded(v) for v in value.values())
        if isinstance(value,list): return any(embedded(v) for v in value)
        return False
    for path in Path(workspace).rglob("*"):
        if path.is_symlink(): raise PreflightError("workspace symbolic link could expose scorer files")
        if not path.is_file(): continue
        if path.resolve() in protected or hashlib.sha256(path.read_bytes()).hexdigest() in hashes:
            raise PreflightError("Gold/Alias file copied into native workspace")
        if path.suffix.lower() in {".json",".yaml",".yml",".jsonl"}:
            try:
                if path.suffix==".jsonl": values=[json.loads(line) for line in path.read_text().splitlines() if line.strip()]
                else: values=[yaml.safe_load(path.read_text())]
            except (ValueError,UnicodeError,yaml.YAMLError): continue
            if any(embedded(value) for value in values):
                raise PreflightError("scorer case/Alias record leaked into native workspace")


def verify_model(actual, requested):
    if not isinstance(actual,dict) or any(k not in actual for k in ("model","version","temperature","max_output","native_model_constraint")):
        return False
    differs=any(actual[k]!=requested[k] for k in ("model","version","temperature","max_output"))
    return isinstance(actual["native_model_constraint"],bool) and (
        not differs or actual["native_model_constraint"] is True and bool(actual.get("reason")))


def validate_probe(system, build, result, requested, checks):
    check(checks,"native_build",build.status=="OK","native build completed",system)
    check(checks,"build_telemetry",coherent_usage(build,"build"),"all build LLM calls measured",system)
    if build.build_llm_total_tokens:
        profile=build.metadata.get("build_effective_model")
        check(checks,"build_effective_model",build.metadata.get("build_model_settings_verified") is True
              and verify_model(profile,requested),"observed ingestion/parser model must match or declare native constraint",system)
    check(checks,"native_query",result.status=="OK","native exploratory query completed",system)
    try: validate_output(result.output); valid=True
    except (ValueError,TypeError): valid=False
    check(checks,"output_contract",valid,"public result schema verified",system)
    check(checks,"query_telemetry",coherent_usage(result,"query")
          and nonnegative(result.tool_calls) and nonnegative(result.retrieval_rounds),"complete LLM/tool telemetry required",system)
    check(checks,"effective_model",result.metadata.get("model_settings_verified") is True
          and verify_model(result.metadata.get("effective_model"),requested),
          "observed model settings must match or declare a documented native constraint",system)
    if system.startswith("opencode"):
        explored=any(e.get("tool")=="task" and e.get("native",{}).get("state",{}).get("input",{}).get("subagent_type")=="explore" for e in result.trace)
        check(checks,"native_explore",explored,"actual explore subagent required in trace",system)
    if system=="opencode_openviking":
        target=build.metadata.get("target_uri","")
        used=any(e.get("tool","").startswith("openviking_") and target
                 and target in json.dumps(e.get("native",{}).get("state",{}).get("input",{})) for e in result.trace)
        check(checks,"native_openviking_mcp",bool(used),"actual corpus-scoped MCP retrieval required",system)


PROBE_CASE=BenchmarkCase("preflight-probe","请探索当前原始材料，返回其中明确描述的数据实体及关系；不能确定的内容留空。")
