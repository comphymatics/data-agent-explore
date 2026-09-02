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
    def __init__(self,retrieval,environment_adapter=None):
        self.tools=retrieval if isinstance(retrieval,DataContextTools) else DataContextTools(retrieval)
        self.retrieval=getattr(self.tools,"retrieval",retrieval)
        self.router=QueryRouter()
        self.planner=CoveragePlanner()
        self.reasoner=JointReasoner()
        self.environment=environment_adapter or NullEnvironmentBindingAdapter()

    def explore(self,query,top_k=None,token_budget=None,state=None):
        scope=self.router.route(query); intent=self.router.intent(query)
        policy=self.planner.plan(intent,top_k=top_k,token_budget=token_budget)
        previous_state=ExplorationState.from_value(state)
        env_required=environment_required(intent,query)
        if env_required:
            requirements={
                "required":True,
                "query":query,
                "intent":intent,
                "scope":scope,
                "required_coverage":list(policy.required_coverage),
                "limit":policy.top_k,
            }
            try:
                env_result=coerce_binding_result(
                    self.environment.resolve(requirements),required=True
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
        search=self.tools.data_search(
            query,
            scope=scope,
            top_k=policy.top_k,
            bundle_k=policy.bundle_k,
            token_budget=policy.token_budget,
            seen_context_ids=previous_state.seen_context_ids,
            read_content=policy.read_content,
            max_per_type=policy.max_contexts_per_type,
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
        hits=search["contexts"]
        coverage=dict(previous_state.coverage)
        for key,value in env_result.coverage.items():
            coverage[key]=bool(coverage.get(key) or value)
        for key,value in search["coverage_hint"].items():
            coverage[key]=bool(coverage.get(key) or value)
        missing,expand=self.planner.evaluate(policy,coverage)
        expansions={}
        paths=[h["path"] for h in hits]

        expansion_request=list(dict.fromkeys(expand+["candidates","conflicts"]))
        if expansion_request and paths:
            expansions=self.tools.data_expand(
                paths,expansion_request,top_k=policy.expand_top_k
            )
            if any(v.get("fields") for v in expansions.values()): coverage["fields"]=True
            if any(v.get("grain") for v in expansions.values()): coverage["grain"]=True
            if any(
                v.get("lineage",{}).get("outgoing") or v.get("lineage",{}).get("incoming")
                for v in expansions.values()
            ): coverage["lineage"]=True
            if any(v.get("business_mapping") for v in expansions.values()): coverage["business_object"]=True
            if any(v.get("dimensions") for v in expansions.values()): coverage["dimensions"]=True
            missing,_=self.planner.evaluate(policy,coverage)

        def context_ref(hit):
            return {
                "path":hit["path"],"type":hit["context_type"],"name":hit["name"],
                "relevance":hit["score"],
            }
        sources=[]; evidence_seen=set()
        for h in hits:
            for source in self.tools.data_source(h["path"]):
                key=(source["source_id"],source["path"],source["sheet"],source["section"],source["row"])
                if key not in evidence_seen:
                    evidence_seen.add(key); sources.append(source)

        analysis={
            "scenarios":[context_ref(h) for h in hits if h["context_type"]=="scenario"],
            "purposes":[context_ref(h) for h in hits if h["context_type"]=="analysis-purpose"],
            "topics":[context_ref(h) for h in hits if h["context_type"]=="topic"],
            "business_objects":[context_ref(h) for h in hits if h["context_type"]=="business-object"],
            "metrics":[context_ref(h) for h in hits if h["context_type"]=="metric"],
            "dimensions":[context_ref(h) for h in hits if h["context_type"]=="dimension"],
        }
        data={
            "logical_models":[context_ref(h) for h in hits if h["context_type"]=="logical-model"],
            "physical_models":[context_ref(h) for h in hits if h["context_type"]=="physical-model"],
            "important_fields":{p:v.get("fields") for p,v in expansions.items() if v.get("fields")},
            "grain":{p:v.get("grain") for p,v in expansions.items() if v.get("grain")},
            "lineage":{p:v.get("lineage") for p,v in expansions.items() if v.get("lineage")},
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
        penalty=0.1*len(missing)+0.03*len(conflicts)+0.02*len(candidates)
        has_context=bool(hits or env_result.assets)
        confidence=max(0.2,1.0-penalty) if has_context else 0.0

        budget=dict(search.get("budget",{}))
        budget["cumulative_estimated_tokens"]=(
            previous_state.used_tokens+budget.get("estimated_tokens",0)
        )
        truncation_reasons=list(search.get("truncation_reasons",[]))
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
            rounds=previous_state.rounds+1,
            used_tokens=budget["cumulative_estimated_tokens"],
            last_intent=intent,
            stop_reason=stop_reason,
        )
        return ContextBundle(
            query={"original":query,"interpreted_intent":intent,"scope":scope},
            summary=self.reasoner.summarize(
                query,hits,expansions,environment_assets=env_result.assets
            ),
            primary_contexts=[{
                "path":h["path"],"type":h["context_type"],"name":h["name"],
                "relevance":h["score"],"reasons":h.get("reasons",[]),
                "content_level":h.get("content_level"),"content":h.get("content"),
            } for h in hits],
            analysis_context=analysis,data_context=data,
            business_mapping={"contexts":bm},
            constraints=constraints,
            environment=env_result.to_dict(),
            coverage=coverage,missing_context=missing,sources=sources,confidence=confidence,
            conflicts=conflicts,candidates=candidates,
            warnings=search.get("warnings",[])+env_result.to_dict()["warnings"],
            truncated=bool(search.get("truncated",False) or env_result.truncated),
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
