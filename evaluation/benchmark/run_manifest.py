"""Versioned reproducibility metadata. Scorer artifacts are hashed, never disclosed."""
from datetime import datetime, timezone
import hashlib
import inspect
import json
from pathlib import Path
import platform
import subprocess
import sys

BENCHMARK_VERSION="four-system-raw-e2e/v2"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def model_profile(model):
    name=model.get("model")
    provider,_,model_name=(name or "").partition("/")
    return {"provider":model.get("provider") or (provider if model_name else None),
            "model_name":model_name or name,"model_version":model.get("version"),
            "temperature":model.get("temperature"),"max_output_tokens":model.get("max_output"),
            "native_model_constraint":model.get("native_model_constraint"),"reason":model.get("reason")}


def manifest(config,run_id,systems,adapters,cases_path,aliases_path,smoke,repeats,budget):
    root=Path(__file__).resolve().parents[2]
    try:
        commit=subprocess.check_output(["git","rev-parse","HEAD"],cwd=root,text=True).strip()
        dirty=bool(subprocess.check_output(["git","status","--porcelain","--untracked-files=all","--","evaluation"],cwd=root,text=True))
    except (subprocess.SubprocessError,OSError): commit=None; dirty=None
    source_hash=hashlib.sha256()
    for path in sorted((root/"evaluation").rglob("*.py")):
        source_hash.update(path.relative_to(root).as_posix().encode()); source_hash.update(path.read_bytes())
    profiles={}
    for name in systems:
        files={inspect.getsourcefile(cls) for cls in adapters[name].__mro__ if cls is not object}
        digest=hashlib.sha256()
        for filename in sorted(f for f in files if f): digest.update(Path(filename).read_bytes())
        profiles[name]={"system":name,"adapter_version":digest.hexdigest(),"requested_model":model_profile(config["model"])}
    return {"benchmark_version":BENCHMARK_VERSION,"run_id":run_id,"timestamp":datetime.now(timezone.utc).isoformat(),
            "git_commit":commit,"evaluation_worktree_dirty":dirty,"evaluation_source_hash":source_hash.hexdigest(),
            "case_set_hash":sha(cases_path),"aliases_sha256":sha(aliases_path),
            "configuration_sha256":hashlib.sha256(json.dumps(config,sort_keys=True).encode()).hexdigest(),
            "smoke":smoke,"systems":list(systems),"repeats":repeats,"model":config["model"],
            "system_profiles":profiles,"builds":{},"query_budget":budget,
            "context_budget_scope":"adapter-native; not an equal hard limit across systems",
            "environment":{"python_version":sys.version,"platform":platform.platform(),"hardware_class":config["hardware_class"]},
            "preflight":{"status":"SKIPPED_SMOKE" if smoke else "PENDING","checks":[],"probes":{}},
            "headline_eligible":False,"normalizer_version":"canonical-entities/v2","scorer_version":"entity-relation-negative/v2"}
