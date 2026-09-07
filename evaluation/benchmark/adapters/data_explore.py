from dataclasses import asdict
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import time

from enterprise_data_context.compiler import ContextCompiler
from enterprise_data_context.persistence import save_compiled
from enterprise_data_context.runtime import load_runtime
from explore_agent import ExploreAgent
from ..raw_corpus import inventory, verify
from ..result_contract import BuildResult, QueryResult
from ..usage import tokens, tool_counts
from .native_driver import invoke


class RecordingTools:
    """Evaluation-only observation of the unchanged four-tool interface."""

    ALLOWED = {"data_search", "data_read", "data_expand", "data_source"}

    def __init__(self, delegate):
        self.delegate = delegate
        self.trace = []

    def __getattr__(self, name):
        if name not in self.ALLOWED:
            raise AttributeError(name)

        def call(*args, **kwargs):
            event = {"kind": "tool_call", "call_id": f"context-{len(self.trace)}",
                     "tool": name, "input": {"args": deepcopy(args), "kwargs": deepcopy(kwargs)}}
            self.trace.append(event)
            try:
                output = getattr(self.delegate, name)(*args, **kwargs)
                event["output"] = deepcopy(output)
                return output
            except Exception as exc:
                event["error"] = {"type": type(exc).__name__, "message": str(exc)}
                raise
        return call


def compiler_version():
    root=Path(__file__).resolve().parents[3]/"enterprise_data_context"
    digest=hashlib.sha256()
    for path in sorted(root.rglob("*.py")):
        digest.update(path.relative_to(root).as_posix().encode()); digest.update(path.read_bytes())
    return digest.hexdigest()


def artifact_fingerprint(root):
    digest=hashlib.sha256()
    for path in sorted(Path(root).rglob("*")):
        if path.is_symlink(): raise ValueError("cached build cannot contain symbolic links")
        if path.is_file():
            digest.update(path.relative_to(root).as_posix().encode()); digest.update(path.read_bytes())
    return digest.hexdigest()


class DataExploreAdapter:
    name="data_explore"

    def __init__(self,config):
        self.config=config; self.runtime=None

    def prepare(self,corpus_path,run_context):
        started=time.monotonic(); self.corpus=corpus_path
        parser_version=self.config.get("parser_version")
        if not parser_version:
            raise RuntimeError("parser_version and a native raw-to-template parser command are required")
        if self.config.get("smoke_parser") and not run_context.smoke:
            raise ValueError("synthetic parser cannot run a formal benchmark")
        version=compiler_version()
        key=hashlib.sha256(json.dumps([run_context.corpus_fingerprint,parser_version,version,
            self.config.get("parser_command")],sort_keys=True).encode()).hexdigest()
        cache=Path(self.config.get("cache_dir",Path(run_context.workspace)/"build"))/key
        receipt_path=cache/"build-receipt.json"
        reused=bool(self.config.get("reuse_snapshot") and receipt_path.exists())
        if reused:
            receipt=json.loads(receipt_path.read_text())
            if receipt.get("corpus_fingerprint")!=run_context.corpus_fingerprint or receipt.get("parser_version")!=parser_version or receipt.get("compiler_version")!=version:
                raise ValueError("cached snapshot provenance mismatch")
            if receipt.get("snapshot_fingerprint")!=artifact_fingerprint(cache/"snapshot"):
                raise ValueError("cached snapshot content changed")
            self.runtime=load_runtime(cache/"snapshot",index_version=receipt["snapshot_version"])
            usage=(0,0,0)
        else:
            if cache.exists():
                # A cold build cannot accidentally consume an existing parser delivery.
                cache=Path(run_context.workspace)/("cold-"+key)
            delivery=cache/"templates"; delivery.mkdir(parents=True,exist_ok=False)
            native=invoke(self.config.get("parser_command"),{
                "protocol":"raw-e2e-driver/v1","phase":"parse","corpus_path":corpus_path,
                "output_dir":str(delivery),"files":inventory(corpus_path),
                "corpus_fingerprint":run_context.corpus_fingerprint},run_context.workspace,
                self.config.get("build_timeout_seconds",1800))
            if native.get("status")!="OK" or native.get("parser_version")!=parser_version or native.get("consumed_files")!=inventory(corpus_path):
                raise ValueError("parser did not produce a complete, versioned raw-input receipt")
            # The existing Compiler remains the only Template contract consumer.
            compiled=ContextCompiler().compile_template_inputs(delivery)
            published=save_compiled(compiled,cache/"snapshot")
            snapshot=published["index_version"]
            usage=tokens(native.get("llm_calls",[]),native.get("usage_complete") is True)
            receipt={"corpus_fingerprint":run_context.corpus_fingerprint,"parser_version":parser_version,
                     "compiler_version":version,"snapshot_version":snapshot,"parser_receipt":native,
                     "snapshot_fingerprint":artifact_fingerprint(cache/"snapshot"),
                     "original_build_tokens":usage[2]}
            receipt_path=cache/"build-receipt.json"
            receipt_path.write_text(json.dumps(receipt,ensure_ascii=False,indent=2))
            self.runtime=load_runtime(cache/"snapshot",index_version=snapshot)
        verify(corpus_path,run_context.corpus_fingerprint)
        return BuildResult(self.name,"OK",*usage,build_time_ms=int(1000*(time.monotonic()-started)),
            storage_bytes=sum(p.stat().st_size for p in cache.rglob("*") if p.is_file()),
            metadata={**receipt,"cold_build":not reused,"reused_snapshot":reused,"encoder_version":getattr(self.runtime.retrieval.pidx.encoder,"version","unknown"),
                      "build_tokens_accounting":"this invocation; original_build_tokens retained for warm-cache comparisons",
                      "effective_model":{"model":None,"version":None,"temperature":None,"max_output":None,
                                         "native_model_constraint":True,"reason":"current deterministic Explore; Router/Reasoner unchanged"}},
            trace=receipt.get("parser_receipt",{}).get("trace",[]))

    def query(self,case,budget,run_context):
        if self.runtime is None:
            raise RuntimeError("prepare must complete first")
        started=time.monotonic()
        agent=ExploreAgent(self.runtime.retrieval)
        recording=RecordingTools(agent.tools)
        agent.tools=recording
        bundle=agent.explore(case.query,token_budget=budget.context_tokens)
        # Preserve native output. The scorer performs the same entity normalization for all systems.
        raw=asdict(bundle)
        telemetry=bundle.telemetry
        trace=recording.trace
        if telemetry.get("environment_tool_calls"):
            trace.append({"kind":"tool_call","call_id":"environment-resolve","tool":"environment_resolve","native":bundle.environment})
        counts=tool_counts(trace)
        # No LLM provider is installed into this adapter. Context payload estimates are not LLM usage.
        return QueryResult(self.name,case.case_id,"OK",raw,0,0,0,
            tool_calls=telemetry["total_tool_calls"],retrieval_rounds=telemetry.get("tool_calls"),
            latency_ms=int(1000*(time.monotonic()-started)),trace=trace,
            metadata={"usage_complete":True,"llm_calls":[],"native_telemetry":telemetry,"tool_counts":counts,
                      "context_payload_tokens_estimated":telemetry["tool_tokens_estimated"],
                      "model_constraint":"deterministic core; no benchmark-specific reasoner"})

    def cleanup(self):
        self.runtime=None
