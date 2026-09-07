"""Actual OpenCode primary agent + native explore subagent, with recursive exports."""
from dataclasses import asdict
import json
import os
from pathlib import Path
import subprocess
import time
from ..raw_corpus import verify
from ..result_contract import BuildResult, QueryResult, ENTITY_TYPES
from ..usage import tokens, tool_counts, nonnegative
from .native_driver import invoke


def parse_events(text):
    events=[]
    for line in text.splitlines():
        try: value=json.loads(line)
        except ValueError: continue
        if isinstance(value,dict): events.append(value)
    return events


def exported_calls(payload):
    calls=[]; trace=[]; children=[]; complete=True
    messages=payload.get("messages")
    if not isinstance(messages,list):
        return [],[],[],False
    for message in messages:
        info=message.get("info",{})
        if info.get("role")=="assistant":
            usage=info.get("tokens",{}); cache=usage.get("cache",{})
            values=[usage.get("input"),usage.get("output"),usage.get("reasoning"),cache.get("read"),cache.get("write")]
            if not all(nonnegative(v) for v in values):
                complete=False
            else:
                calls.append({"call_id":info.get("id"),"input_tokens":values[0]+values[3]+values[4],
                    "output_tokens":values[1]+values[2],"model":info.get("modelID"),"provider":info.get("providerID"),
                    "native_tokens":usage})
        for part in message.get("parts",[]):
            if part.get("type")!="tool": continue
            state=part.get("state",{}); tool=part.get("tool","")
            trace.append({"kind":"tool_call","call_id":part.get("callID") or part.get("id"),"tool":tool,"native":part})
            if tool=="task":
                meta=state.get("metadata",{})
                child=meta.get("sessionId") or meta.get("sessionID")
                if not child:
                    import re
                    found=re.search(r'(?:session_id:\s*|<task id=")([\w-]+)',str(state.get("output","")))
                    child=found.group(1) if found else None
                if child: children.append(child)
                else: complete=False
    return calls,trace,children,complete


class OpenCodeNativeAdapter:
    name="opencode_native"

    def __init__(self,config):
        self.config=config
        self.mcp={}

    def prepare(self,corpus_path,run_context):
        self.corpus=corpus_path; self.context=run_context
        started=time.monotonic()
        command=self.config.get("command","opencode")
        version=subprocess.run([command,"--version"],capture_output=True,text=True,timeout=15,check=True).stdout.strip()
        self.version=version
        return BuildResult(self.name,"OK",0,0,0,build_time_ms=int(1000*(time.monotonic()-started)),
            metadata={"cold_build":True,"reused_snapshot":False,"version":version,"raw_workspace":corpus_path,
                      "effective_model":run_context.model,"model_settings_verification":"query session exports plus explicit agent config"})

    def environment(self,budget,context):
        model=context.model
        settings={"model":model["model"],"temperature":model["temperature"],
                  "options":{"maxOutputTokens":budget.max_output_tokens},
                  "permission":{"external_directory":"deny","edit":"deny"}}
        config={"$schema":"https://opencode.ai/config.json","model":model["model"],"share":"disabled",
                "autoupdate":False,"agent":{"plan":settings,"explore":settings},"mcp":self.mcp,
                "tools":{"*":False,"task":True,"read":True,"glob":True,"grep":True,"bash":True,"list":True,
                         "openviking_*":bool(self.mcp)},
                "permission":{"external_directory":"deny","edit":"deny"},"plugin":[],"instructions":[]}
        env=os.environ.copy()
        env["OPENCODE_CONFIG_CONTENT"]=json.dumps(config)
        env["OPENCODE_DISABLE_PROJECT_CONFIG"]="true"
        env["OPENCODE_CONFIG_DIR"]=str(Path(context.workspace)/"opencode-config")
        Path(env["OPENCODE_CONFIG_DIR"]).mkdir(exist_ok=True)
        return env

    def prompt(self,query):
        return ("Use OpenCode's built-in explore subagent to explore ONLY the original enterprise documents "
                "in the current directory. Native tools may read/convert Word and Excel as needed. "
                "Do not inspect parent directories or unrelated workspaces. Answer the user's exact question. "
                "Return the discovered semantic entities, with document-native names, as JSON keyed by "
                +", ".join(ENTITY_TYPES)+". Omit irrelevant entities. Do not invent IDs or missing facts. "
                "The final response must be JSON; no evidence-ID markers are requested.\nQuery: "+query)

    def query(self,case,budget,run_context):
        started=time.monotonic(); env=self.environment(budget,run_context)
        command=self.config.get("command","opencode")
        failure=None
        try:
            result=subprocess.run([command,"run","--pure","--format","json","--model",run_context.model["model"],
                "--agent","plan","--dir",self.corpus,self.prompt(case.query)],cwd=self.corpus,env=env,
                capture_output=True,text=True,timeout=budget.timeout_seconds,check=False)
            stdout=result.stdout
            if result.returncode: failure="OpenCode exited "+str(result.returncode)
        except subprocess.TimeoutExpired as exc:
            stdout=exc.stdout or ""
            if isinstance(stdout,bytes): stdout=stdout.decode(errors="replace")
            failure="query timeout"
        events=parse_events(stdout)
        sessions=list(dict.fromkeys(e.get("sessionID") for e in events if e.get("sessionID")))
        trace=[]; calls=[]; seen=set(); complete=bool(sessions); exports=[]
        while sessions:
            sid=sessions.pop(0)
            if sid in seen: continue
            if len(seen)>=64:
                complete=False; break
            seen.add(sid)
            try:
                exported=subprocess.run([command,"export",sid],cwd=self.corpus,env=env,capture_output=True,text=True,timeout=30,check=True)
                payload=json.loads(exported.stdout[exported.stdout.index("{"):])
                rows,tools,children,ok=exported_calls(payload)
                calls+=rows; trace+=tools; sessions+=children; complete &= ok
                exports.append(payload)
            except (ValueError,subprocess.SubprocessError,OSError): complete=False
        explored=any(t["tool"]=="task" and t["native"].get("state",{}).get("input",{}).get("subagent_type")=="explore" for t in trace)
        if not explored: failure=failure or "native explore subagent not present in trace"
        allowed={"task","read","glob","grep","bash","list","todowrite","todoread"}
        if any(t["tool"] not in allowed and not (self.mcp and t["tool"].startswith("openviking_")) for t in trace):
            failure=failure or "native session used an out-of-scope tool"
        texts=[e["part"]["text"] for e in events if e.get("type")=="text" and isinstance(e.get("part",{}).get("text"),str)]
        raw=texts[-1] if texts else ""
        # Strip only a complete Markdown JSON fence; no scorer aliases participate.
        if raw.startswith("```json") and raw.rstrip().endswith("```"): raw=raw[7:raw.rfind("```")].strip()
        if not raw: failure=failure or "missing native final output"
        verify(self.corpus,run_context.corpus_fingerprint)
        observed_usage=tokens(calls,complete)
        counts=tool_counts(trace) if complete else None
        # Exports do not attest background title/summary/provider calls. An external
        # process-wide ledger is required before treating observed usage as total cost.
        usage=(None,None,None)
        usage_receipt=None
        usage_error=None
        if self.config.get("usage_command"):
            try:
                usage_receipt=invoke(self.config["usage_command"],{
                    "protocol":"raw-e2e-driver/v1","phase":"query_usage",
                    "session_ids":sorted(seen),"run_id":run_context.run_id,
                    "case_id":case.case_id,"repeat":run_context.repeat,
                    "workspace":run_context.workspace},run_context.workspace,30)
                ledger=usage_receipt.get("llm_calls",[])
                covered=set(usage_receipt.get("covered_session_ids",[]))
                ledger_ids={c.get("call_id") for c in ledger}
                attested=(complete and usage_receipt.get("usage_complete") is True
                    and usage_receipt.get("scope")=="process_all_llm_calls"
                    and seen<=covered and {c["call_id"] for c in calls}<=ledger_ids)
                if attested:
                    # Conflicting observed and provider records invalidate the ledger.
                    combined={c["call_id"]:(c["input_tokens"],c["output_tokens"]) for c in ledger}
                    attested=all(combined[c["call_id"]]==(c["input_tokens"],c["output_tokens"]) for c in calls)
                usage=tokens(ledger,attested)
                if usage[2] is not None: calls=ledger
            except (ValueError,RuntimeError,KeyError,TypeError,subprocess.SubprocessError,OSError) as exc:
                usage_error=type(exc).__name__+": "+str(exc)
        return QueryResult(self.name,case.case_id,"INVALID" if failure else "OK",raw,*usage,
            tool_calls=counts["total"] if counts else None,retrieval_rounds=counts["retrieval"] if counts else None,
            latency_ms=int(1000*(time.monotonic()-started)),trace=trace,
            metadata={"error":failure,"events":events,"session_exports":exports,"llm_calls":calls,
                      "usage_complete":usage[2] is not None,"observed_session_tokens":observed_usage,
                      "usage_receipt":usage_receipt,"usage_error":usage_error,
                      "usage_scope":"process ledger" if usage[2] is not None else "session exports only; background calls unverified",
                      "tool_counts":counts,"effective_model":run_context.model,
                      "observed_models":sorted({str(c.get("provider"))+"/"+str(c.get("model")) for c in calls})})

    def cleanup(self):
        pass
