from enterprise_data_context.models import ContextBundle
from enterprise_data_context.environment import NullEnvironmentBindingAdapter
from .router import QueryRouter
from .planner import CoveragePlanner
from .reasoner import JointReasoner

class ExploreAgent:
    def __init__(self,retrieval,environment_adapter=None):
        self.retrieval=retrieval
        self.router=QueryRouter()
        self.planner=CoveragePlanner()
        self.reasoner=JointReasoner()
        self.environment=environment_adapter or NullEnvironmentBindingAdapter()

    def explore(self,query,top_k=8):
        scope=self.router.route(query); intent=self.router.intent(query)
        search=self.retrieval.data_search(query,scope=scope,top_k=top_k)
        hits=search["contexts"]
        coverage=dict(search["coverage_hint"])
        missing,expand=self.planner.evaluate(intent,coverage)
        expansions={}
        paths=[h["path"] for h in hits]

        if expand and paths:
            expansions=self.retrieval.data_expand(paths,expand)
            # Re-evaluate coverage based on actual expansion contents.
            if any(v.get("fields") for v in expansions.values()): coverage["fields"]=True
            if any(v.get("grain") for v in expansions.values()): coverage["grain"]=True
            if any(v.get("lineage") for v in expansions.values()): coverage["lineage"]=True
            if any(v.get("business_mapping") for v in expansions.values()): coverage["business_object"]=True
            if any(v.get("dimensions") for v in expansions.values()): coverage["dimensions"]=True
            missing,_=self.planner.evaluate(intent,coverage)

        env_required=any(x in query for x in ("当前环境","客户环境","当前客户","现网"))
        matched=[]
        if env_required:
            matched=self.environment.resolve({"query":query,"scope":scope,"contexts":hits})

        sources=[]
        seen=set()
        for h in hits:
            for s in self.retrieval.data_source(h["path"]):
                key=(s["source_id"],s["path"],s["sheet"],s["section"],s["row"])
                if key not in seen:
                    seen.add(key); sources.append(s)

        analysis={
            "scenarios":[h for h in hits if h["context_type"]=="scenario"],
            "purposes":[h for h in hits if h["context_type"]=="analysis-purpose"],
            "topics":[h for h in hits if h["context_type"]=="topic"],
            "business_objects":[h for h in hits if h["context_type"]=="business-object"],
            "metrics":[h for h in hits if h["context_type"]=="metric"],
            "dimensions":[h for h in hits if h["context_type"]=="dimension"],
        }
        data={
            "logical_models":[h for h in hits if h["context_type"]=="logical-model"],
            "physical_models":[h for h in hits if h["context_type"]=="physical-model"],
            "important_fields":{p:v.get("fields") for p,v in expansions.items() if v.get("fields")},
            "grain":{p:v.get("grain") for p,v in expansions.items() if v.get("grain")},
            "lineage":{p:v.get("lineage") for p,v in expansions.items() if v.get("lineage")},
        }
        bm={p:v.get("business_mapping") for p,v in expansions.items() if v.get("business_mapping")}
        confidence=max(0.2,1.0-0.1*len(missing)) if hits else 0.0
        return ContextBundle(
            query={"original":query,"interpreted_intent":intent,"scope":scope},
            summary=self.reasoner.summarize(query,hits,expansions),
            primary_contexts=[{"path":h["path"],"type":h["context_type"],"name":h["name"],"relevance":h["score"]} for h in hits],
            analysis_context=analysis,data_context=data,
            business_mapping={"contexts":bm},
            constraints=[],
            environment={"binding_required":env_required,"binding_status":"resolved" if matched else "unresolved","matched_assets":matched},
            coverage=coverage,missing_context=missing,sources=sources,confidence=confidence
        )
