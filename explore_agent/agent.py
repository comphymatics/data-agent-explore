from .binding import aggregate_availability
from hashlib import sha256
import json
from .coverage import assess, infer_requirements, validate_requirements, requirement, missing_requirements, summarize_coverage
from .telemetry import MeteredTools, estimate
from enterprise_data_context.models import ContextBundle
from enterprise_data_context.environment import (
    BINDING_POLICY_VERSION,
    AvailabilityState,
    EnvironmentBindingResult,
    NullEnvironmentBindingAdapter,
    coerce_binding_result,
)
from enterprise_data_context.tools import DataContextTools
from .binding import (
    build_binding_overlay,
    environment_required,
    reference_only_candidates,
)
from .router import QueryRouter
from .planner import CoveragePlanner
from .reasoner import JointReasoner
from .state import ExplorationState

class ExploreAgent:
    def __init__(self,retrieval,environment_adapter=None,semantic_provider=None,semantic_limits=None):
        self.tools=retrieval if isinstance(retrieval,DataContextTools) else DataContextTools(retrieval)
        self.router=QueryRouter(semantic_provider,semantic_limits)
        self.planner=CoveragePlanner()
        self.reasoner=JointReasoner(semantic_provider,semantic_limits)
        self.environment=environment_adapter or NullEnvironmentBindingAdapter()

    def explore(self,query,top_k=None,token_budget=None,state=None,requirements=None,mode="auto",hierarchy=None):
        if not isinstance(query,str) or not query.strip():
            raise ValueError("query must be a non-empty string")
        explicit_requirements=validate_requirements(requirements) if requirements is not None else None
        route=self.router.analyze(query)
        scope=route["scope"]; intent=route["intent"]
        tools=MeteredTools(self.tools)
        policy=self.planner.plan(intent,top_k=top_k,token_budget=token_budget)
        previous_state=ExplorationState.from_value(state)
        query_signature=sha256(json.dumps([query,scope,intent,route["entities"],route["aspects"],explicit_requirements,mode,hierarchy],sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        if previous_state.query_signature and previous_state.query_signature != query_signature:
            raise ValueError("exploration state query/requirements mismatch")
        env_required=environment_required(intent,query) or environment_required(self.router.intent(query),query) or any(r["layer"]=="ENVIRONMENT" for r in (explicit_requirements or []))
        environment_calls_before=getattr(self.environment,"tool_call_count",None)
        if env_required:
            environment_request={
                "required":True,
                "query":query,
                "intent":intent,
                "scope":scope,
                "required_coverage":list(policy.required_coverage),
                "limit":policy.top_k,
                "focused_expansion":True,
                "requirements":explicit_requirements or [],
            }
            try:
                env_result=coerce_binding_result(
                    self.environment.resolve(environment_request),required=True
                )
            except Exception as exc:
                env_result=EnvironmentBindingResult(
                    required=True,
                    state=AvailabilityState.UNAVAILABLE,
                    warnings=[{
                        "code":"environment_adapter_failure",
                        "message":str(exc) or exc.__class__.__name__,
                    }],
                )
        else:
            env_result=EnvironmentBindingResult(
                required=False,state=AvailabilityState.UNSUPPORTED
            )
        search=tools.data_search(
            query,
            scope=scope,
            top_k=policy.top_k,
            bundle_k=policy.bundle_k,
            token_budget=policy.token_budget,
            seen_context_ids=previous_state.seen_context_ids,
            read_content=policy.read_content,
            max_per_type=policy.max_contexts_per_type,
            intent=intent,
            mode=mode,
            hierarchy=hierarchy,
            retrieval_strategy=route["retrieval_strategy"],
        )
        current_version=search.get("index_version")
        if (
            previous_state.index_version is not None
            and current_version is not None
            and previous_state.index_version != current_version
        ):
            raise ValueError(
                "exploration state index_version does not match the pinned runtime snapshot"
            )
        if previous_state.serving_version and previous_state.serving_version != search.get("retrieval_version"):
            raise ValueError("exploration state serving_version mismatch")
        hits=search["contexts"]
        selected_requirements=explicit_requirements or infer_requirements(
            query,hits,search.get("anchor_context_ids",[]),
            list(dict.fromkeys([*policy.required_coverage,*route["aspects"]])),env_required)
        if not explicit_requirements and route["entities"]:
            selected_requirements=[]
            for entity in route["entities"]:
                path=next((h["path"] for h in hits if h["name"].casefold()==entity.casefold()),entity)
                for aspect in list(dict.fromkeys([*policy.required_coverage,*route["aspects"]])):
                    selected_requirements.append(requirement(path,aspect,name=entity))
                    if env_required and aspect in {"models","metrics","fields","grain","lineage","dimensions"}:
                        selected_requirements.append(requirement(path,aspect,"ENVIRONMENT",entity))
        expansions={}
        coverage=assess(selected_requirements,hits,expansions,env_result)
        missing,expand=self.planner.evaluate(policy,coverage)
        paths=[h["path"] for h in hits]
        expansion_request=list(dict.fromkeys(expand+["hierarchy","related","candidates","conflicts"]))
        if expansion_request and paths:
            expansions=tools.data_expand(paths,expansion_request,top_k=policy.expand_top_k,
                                         query=" ".join(dict.fromkeys([r["selector"] for r in selected_requirements if r.get("selector")])) or query,intent=intent,token_budget=policy.token_budget)
        coverage=assess(selected_requirements,hits,expansions,env_result)
        missing=missing_requirements(coverage)

        def context_ref(hit):
            return {
                "path":hit["path"],"type":hit["context_type"],"name":hit["name"],
                "relevance":hit["score"],"knowledge_layer":"REFERENCE",
            }
        # Evidence comes with supported assertions in the two rich reads.
        sources=[]; evidence_seen=set()
        for hit in hits:
            proofs=hit.get("support",[])+expansions.get(hit["path"],{}).get("support",[])
            for proof in proofs:
                for source in proof.get("evidence",[]):
                    key=json.dumps(source,sort_keys=True,ensure_ascii=False)
                    if key not in evidence_seen:
                        evidence_seen.add(key); sources.append(source)

        analysis={
            "knowledge_layer":"REFERENCE",            "scenarios":[context_ref(h) for h in hits if h["context_type"]=="scenario"],
            "purposes":[context_ref(h) for h in hits if h["context_type"]=="analysis-purpose"],
            "topics":[context_ref(h) for h in hits if h["context_type"]=="topic"],
            "business_objects":[context_ref(h) for h in hits if h["context_type"]=="business-object"],
            "metrics":[context_ref(h) for h in hits if h["context_type"]=="metric"],
            "dimensions":[context_ref(h) for h in hits if h["context_type"]=="dimension"],
        }
        analysis_paths={
            h["path"] for h in hits
            if h["context_type"] in {
                "scenario", "analysis-purpose", "topic",
                "business-object", "metric", "dimension",
            }
        }
        analysis["hierarchy"]={
            path:value.get("hierarchy")
            for path,value in expansions.items()
            if path in analysis_paths and value.get("hierarchy")
        }
        analysis["relations"]={
            path:value.get("related")
            for path,value in expansions.items()
            if path in analysis_paths and value.get("related")
        }
        data={
            "knowledge_layer":"REFERENCE",            "logical_models":[context_ref(h) for h in hits if h["context_type"]=="logical-model"],
            "physical_models":[context_ref(h) for h in hits if h["context_type"]=="physical-model"],
            "important_fields":{p:v.get("fields") for p,v in expansions.items() if v.get("fields")},
            "grain":{p:v.get("grain") for p,v in expansions.items() if v.get("grain")},
            "lineage":{p:v.get("lineage") for p,v in expansions.items() if v.get("lineage")},
        }
        model_paths={
            h["path"] for h in hits
            if h["context_type"] in {"logical-model","physical-model"}
        }
        data["hierarchy"]={
            path:value.get("hierarchy")
            for path,value in expansions.items()
            if path in model_paths and value.get("hierarchy")
        }
        data["relations"]={
            path:value.get("related")
            for path,value in expansions.items()
            if path in model_paths and value.get("related")
        }
        bm={p:v.get("business_mapping") for p,v in expansions.items() if v.get("business_mapping")}
        conflicts=[]; candidates=[]; constraints=[]
        for path,expanded in expansions.items():
            for conflict in expanded.get("conflicts",[]):
                conflicts.append({"path":path,**conflict})
            for section,items in expanded.get("candidates",{}).items():
                for item in items:
                    candidates.append({"path":path,"section":section,**item})
            if expanded.get("constraints"):
                values=expanded["constraints"]
                constraints.extend(values if isinstance(values,list) else [values])
        binding_overlay=build_binding_overlay(
            env_result,
            hits,
            reference_index_version=search.get("index_version"),
            required_coverage=policy.required_coverage,
        )
        candidates.extend(reference_only_candidates(binding_overlay))
        missing=list(dict.fromkeys(missing+binding_overlay["missing_context"]))
        penalty=0.1*sum(r["status"] not in {"SATISFIED","NOT_APPLICABLE"} for r in coverage.values())+0.03*len(conflicts)+0.02*len(candidates)
        has_context=bool(hits or env_result.assets)
        confidence=max(0.2,1.0-penalty) if has_context else 0.0

        budget=dict(search.get("budget",{}))
        budget["cumulative_estimated_tokens"]=(
            previous_state.used_tokens+budget.get("estimated_tokens",0)
        )
        truncation_reasons=list(search.get("truncation_reasons",[]))
        if any(x.get("truncated") for x in expansions.values()):
            truncation_reasons.append("expansion_token_budget")
        if env_result.truncated and "environment_truncated" not in truncation_reasons:
            truncation_reasons.append("environment_truncated")
        if not has_context:
            if previous_state.seen_context_ids and "seen_context" in truncation_reasons:
                stop_reason="no_new_context"
            elif "token_budget" in truncation_reasons:
                stop_reason="token_budget_exhausted"
            else:
                stop_reason="no_context_found"
        elif not missing:
            stop_reason="coverage_complete"
        elif budget.get("remaining_tokens")==0:
            stop_reason="token_budget_exhausted"
        else:
            stop_reason="incomplete_after_focused_expand"

        next_state=ExplorationState(
            index_version=search.get("index_version") or previous_state.index_version,
            seen_context_ids=list(search.get("seen_context_ids",[])),
            coverage=coverage,
            query_signature=query_signature,
            serving_version=search.get("retrieval_version"),
            environment_snapshot=env_result.to_dict().get("snapshot_token"),
            rounds=previous_state.rounds+1,
            used_tokens=budget["cumulative_estimated_tokens"],
            last_intent=intent,
            stop_reason=stop_reason,
        )
        summary=self.reasoner.reason(query,hits,expansions,coverage,environment_assets=env_result.assets)
        telemetry=tools.report()
        environment_calls_after=getattr(self.environment,"tool_call_count",None)
        telemetry["environment_tool_calls"]=(environment_calls_after-environment_calls_before
            if env_required and environment_calls_before is not None and environment_calls_after is not None else int(env_required))
        telemetry["environment_tool_calls_complete"]=environment_calls_before is not None or not env_required
        telemetry["semantic_calls"]=[dict(self.router.semantic.last_trace),dict(self.reasoner.semantic.last_trace)]
        telemetry["total_tool_calls"]=telemetry["tool_calls"]+telemetry["environment_tool_calls"]
        telemetry["environment_tokens_estimated"]=estimate(env_result.to_dict()) if env_required else 0
        called=[row for row in telemetry["semantic_calls"] if row["calls"]]
        telemetry["model_tokens_reported"]=sum(row["provider_tokens"] for row in called if row["provider_tokens"] is not None)
        telemetry["model_token_usage_complete"]=all(row["provider_tokens"] is not None for row in called)
        telemetry["total_tokens_estimated"]=telemetry["tool_tokens_estimated"]+telemetry["environment_tokens_estimated"]+sum(
            row["provider_tokens"] if row["provider_tokens"] is not None else
            row["input_tokens_estimated"]+max(row["output_tokens_estimated"],self.reasoner.semantic.limits.max_output_tokens)
            for row in called)
        return ContextBundle(
            query={"original":query,"interpreted_intent":intent,"scope":scope},
            summary=summary,
            serving={"retrieval_version":search.get("retrieval_version"),"encoder_version":search.get("encoder_version"),"coverage_version":"requirement-coverage/v3",
                     "anchor_candidates":search.get("anchor_candidates",[]),"anchor_k":policy.top_k},
            coverage_summary=summarize_coverage(coverage),
            anchor_context_ids=search.get("anchor_context_ids",[]),
            focused_expansion=expansions,
            telemetry=telemetry,
            retrieval_trace=aggregate_availability(search.get("retrieval_trace",{}),binding_overlay),
            reasoning_observations=self.reasoner.observations,
            primary_contexts=[{
                "path":h["path"],"type":h["context_type"],"name":h["name"],
                "relevance":h["score"],"reasons":h.get("reasons",[]),
                "content_level":h.get("content_level"),"content":h.get("content"),"knowledge_layer":"REFERENCE",
            } for h in hits],
            analysis_context=analysis,data_context=data,
            business_mapping={"knowledge_layer":"REFERENCE","contexts":bm},
            constraints=constraints,
            environment=env_result.to_dict(),
            coverage=coverage,missing_context=missing,sources=sources,confidence=confidence,
            conflicts=conflicts,candidates=candidates,
            warnings=search.get("warnings",[])+env_result.to_dict()["warnings"],
            truncated=bool(truncation_reasons),
            truncation_reasons=truncation_reasons,
            index_version=search.get("index_version"),
            policy=policy.to_dict(),budget=budget,novelty=search.get("novelty",{}),
            selected_context_ids=list(search.get("selected_context_ids",[])),
            seen_context_ids=list(search.get("seen_context_ids",[])),
            exploration_state=next_state.to_dict(),stop_reason=stop_reason,
            reference_index_version=search.get("index_version"),
            binding_policy_version=BINDING_POLICY_VERSION,
            binding_overlay=binding_overlay,
        )
