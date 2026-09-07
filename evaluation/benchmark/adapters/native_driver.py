"""Versioned stdin/stdout integration boundary for separately owned native pipelines."""
import json
from pathlib import Path
import subprocess
import time
from dataclasses import asdict
from ..raw_corpus import inventory, verify
from ..result_contract import BuildResult, QueryResult
from ..usage import tokens, tool_counts
from ..output_contract import descriptor, set_output


def isolated_command(command, workspace, execution_prefix=None):
    return [*execution_prefix,"--workspace",workspace,"--",*command] if execution_prefix else command


def invoke(command, payload, workspace, timeout, execution_prefix=None):
    if not isinstance(command,list) or not command or not all(isinstance(x,str) for x in command):
        raise RuntimeError("native command must be configured as an argv array")
    completed=subprocess.run(isolated_command(command,workspace,execution_prefix),input=json.dumps(payload,ensure_ascii=False),cwd=workspace,
                             capture_output=True,text=True,timeout=timeout,check=False)
    if completed.returncode:
        raise RuntimeError("native process exited "+str(completed.returncode))
    result=json.loads(completed.stdout)
    if not isinstance(result,dict) or result.get("protocol")!="raw-e2e-driver/v1":
        raise ValueError("native driver returned an invalid protocol receipt")
    return result


class NativeDriverAdapter:
    name="native"
    required_stages=()

    def __init__(self,config):
        self.config=config
        self.corpus=None
        self.context=None

    def prepare(self,corpus_path,run_context):
        self.corpus=corpus_path; self.context=run_context
        started=time.monotonic()
        receipt=invoke(self.config.get("command"),{
            "protocol":"raw-e2e-driver/v1","phase":"prepare","corpus_path":corpus_path,
            "corpus_fingerprint":run_context.corpus_fingerprint,"files":inventory(corpus_path),
            "workspace":run_context.workspace,"model":run_context.model},
            run_context.workspace,self.config.get("build_timeout_seconds",1800),self.config.get("execution_prefix"))
        verify(corpus_path,run_context.corpus_fingerprint)
        if receipt.get("consumed_files")!=inventory(corpus_path):
            raise ValueError("native ingestion did not attest consumption of the complete raw inventory")
        if not set(self.required_stages)<=set(receipt.get("stages",[])):
            raise ValueError("native pipeline stages missing from receipt")
        usage=tokens(receipt.get("llm_calls",[]),receipt.get("usage_complete") is True)
        return BuildResult(self.name,receipt.get("status","INVALID"),*usage,
            build_time_ms=int(1000*(time.monotonic()-started)),storage_bytes=receipt.get("storage_bytes"),
            metadata={"cold_build":receipt.get("cold_build"),"reused_snapshot":receipt.get("reused_snapshot"),
                      "build_effective_model":receipt.get("effective_model"),
                      "build_model_settings_verified":receipt.get("model_settings_verified",False),
                      "effective_model":receipt.get("effective_model"),"native_version":receipt.get("native_version"),
                      "native_receipt":receipt},trace=receipt.get("trace",[]))

    def query(self,case,budget,run_context):
        started=time.monotonic()
        receipt=invoke(self.config.get("command"),{
            "protocol":"raw-e2e-driver/v1","phase":"query","case":asdict(case),"budget":asdict(budget),
            "output_contract":descriptor(),
            "workspace":run_context.workspace,"model":run_context.model,"repeat":run_context.repeat},
            run_context.workspace,budget.timeout_seconds,self.config.get("execution_prefix"))
        verify(self.corpus,run_context.corpus_fingerprint)
        trace=receipt.get("trace",[])
        counts=tool_counts(trace) if receipt.get("tools_complete") is True else None
        usage=tokens(receipt.get("llm_calls",[]),receipt.get("usage_complete") is True)
        result=QueryResult(self.name,case.case_id,receipt.get("status","INVALID"),receipt.get("raw_output"),*usage,
            tool_calls=counts["total"] if counts else None,retrieval_rounds=receipt.get("retrieval_rounds"),
            latency_ms=int(1000*(time.monotonic()-started)),trace=trace,
            metadata={"tool_counts":counts,"usage_complete":usage[2] is not None,
                      "effective_model":receipt.get("effective_model"),"llm_calls":receipt.get("llm_calls",[]),
                      "model_settings_verified":receipt.get("model_settings_verified",False),
                      "delivered_context_measurement":receipt.get("delivered_context_measurement") or {
                          "reason":"native driver did not report a reliable delivered-context measurement"}})
        from ..usage import nonnegative
        if nonnegative(receipt.get("delivered_context_tokens")) and receipt.get("delivered_context_measurement",{}).get("method"):
            result.delivered_context_tokens=receipt["delivered_context_tokens"]
        return set_output(result,receipt.get("output",receipt.get("raw_output")))

    def cleanup(self):
        # Never delete a shared remote index implicitly; native drivers own their resources.
        if self.config.get("cleanup_command") and self.context:
            invoke(self.config["cleanup_command"],{"protocol":"raw-e2e-driver/v1","phase":"cleanup",
                "workspace":self.context.workspace},self.context.workspace,30,self.config.get("execution_prefix"))
