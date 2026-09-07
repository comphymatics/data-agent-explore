"""Native OpenViking raw ingestion followed by actual OpenCode explore over MCP."""
import time
from pathlib import Path
from .opencode_native import OpenCodeNativeAdapter
from ..openviking_import import auth_headers, multipart_file, request_json, unwrap
from ..raw_corpus import inventory, verify
from ..usage import tokens


def validate_ingestion(payload,target):
    result=unwrap(payload)
    if not isinstance(result,dict) or result.get("status")!="success":
        raise ValueError("OpenViking ingestion did not complete successfully")
    if result.get("errors") or result.get("meta",{}).get("failed_files"):
        raise ValueError("OpenViking ingestion contains failed raw files")
    uri=result.get("root_uri","")
    if not (uri==target or uri.startswith(target+"/")):
        raise ValueError("OpenViking stored a resource outside the run namespace")
    return result


class OpenCodeOpenVikingAdapter(OpenCodeNativeAdapter):
    name="opencode_openviking"

    def prepare(self,corpus_path,run_context):
        started=time.monotonic()
        build=super().prepare(corpus_path,run_context)
        config=self.config.get("openviking",{})
        base=config.get("base_url")
        if not base: raise RuntimeError("OpenViking base_url required")
        self.target="viking://resources/e2e-"+run_context.run_id+"-"+run_context.corpus_fingerprint[:12]
        trace=[]; calls=[]; complete=True
        headers=auth_headers(config); timeout=config.get("timeout_seconds",300)
        for entry in inventory(corpus_path):
            path=Path(corpus_path)/entry["path"]
            body,ctype=multipart_file("file",path)
            upload=unwrap(request_json(base,"POST","/api/v1/resources/temp_upload",headers,timeout,raw_body=body,content_type=ctype))
            payload=request_json(base,"POST","/api/v1/resources",headers,timeout,body={
                "temp_file_id":upload["temp_file_id"],"to":self.target+"/"+entry["path"],"wait":True,
                "timeout":timeout,"telemetry":True,"processing_mode":"semantic_and_vectors","strict":True})
            validate_ingestion(payload,self.target)
            trace.append({"phase":"native_ingestion","raw_file":entry,"response":payload})
            usage=payload.get("telemetry",{}).get("summary",{}).get("tokens",{}).get("llm",{})
            if not isinstance(usage,dict) or "input" not in usage or "output" not in usage:
                complete=False
            else:
                calls.append({"call_id":"ingest:"+entry["path"],"input_tokens":usage["input"],"output_tokens":usage["output"]})
        verify(corpus_path,run_context.corpus_fingerprint)
        self.mcp={"openviking":{"type":"remote","url":base.rstrip("/")+"/mcp","enabled":True,"oauth":False,"headers":headers}}
        build.build_llm_input_tokens,build.build_llm_output_tokens,build.build_llm_total_tokens=tokens(calls,complete)
        build.build_time_ms=int(1000*(time.monotonic()-started)); build.trace=trace
        build.metadata.update(target_uri=self.target,native_ingestion=True,usage_complete=complete,
            llm_calls=calls,openviking_model=config.get("model"),openviking_version=config.get("version"))
        observed=[event["response"].get("effective_model") for event in trace]
        build.metadata["build_effective_model"]=observed[0] if observed else None
        build.metadata["build_model_settings_verified"]=bool(observed) and all(
            event["response"].get("model_settings_verified") is True and profile==observed[0]
            for event,profile in zip(trace,observed))
        return build

    def prompt(self,query):
        return (super().prompt(query)+"\nThe explore subagent MUST use OpenViking MCP search/read tools. "
                "Restrict every retrieval to the freshly ingested namespace "+self.target+". "
                "Do not use another namespace, shared memory or a preexisting index.")

    def query(self,case,budget,run_context):
        result=super().query(case,budget,run_context)
        native=[e for e in result.trace if "openviking" in e.get("tool","").lower()]
        retrieval=[e for e in native if any(k in e["tool"].lower() for k in ("search","find","read"))]
        if not retrieval:
            result.status="INVALID"; result.metadata["error"]="OpenCode did not invoke OpenViking retrieval"
        for event in retrieval:
            inputs=event.get("native",{}).get("state",{}).get("input",{})
            serialized=str(inputs)
            if self.target not in serialized:
                result.status="INVALID"; result.metadata["error"]="OpenViking retrieval was not scoped to the frozen corpus namespace"
        # Query-time service LLMs must also be counted, independently of the OpenCode model calls.
        service_calls=[]; complete=True
        for event in native:
            output=event.get("native",{}).get("state",{}).get("output")
            try:
                import json
                payload=json.loads(output) if isinstance(output,str) else output
                usage=payload["telemetry"]["summary"]["tokens"]["llm"]
                service_calls.append({"call_id":"viking:"+event["call_id"],"input_tokens":usage["input"],"output_tokens":usage["output"]})
            except (ValueError,TypeError,KeyError): complete=False
        usage=tokens([*result.metadata.get("llm_calls",[]),*service_calls],result.metadata.get("usage_complete",False) and complete)
        result.query_llm_input_tokens,result.query_llm_output_tokens,result.query_llm_total_tokens=usage
        result.metadata.update(openviking_llm_calls=service_calls,openviking_usage_complete=complete,usage_complete=usage[2] is not None)
        return result
