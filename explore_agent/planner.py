REQUIREMENTS={
    "metric_to_models":["metrics","models"],
    "analysis_data_requirement":["purpose","metrics","dimensions","models"],
    "model_understanding":["business_meaning","business_object","fields","grain"],
    "impact_analysis":["models","lineage"],
    "generic":["business_meaning"],
}

EXPANSION={
    "fields":["fields"],
    "grain":["grain"],
    "lineage":["lineage"],
    "business_object":["business_mapping"],
    "dimensions":["dimensions"],
    "metrics":["metrics"],
}

class CoveragePlanner:
    def evaluate(self,intent,coverage):
        req=REQUIREMENTS.get(intent,REQUIREMENTS["generic"])
        missing=[x for x in req if not coverage.get(x,False)]
        expand=[]
        for m in missing:
            expand += EXPANSION.get(m,[])
        # preserve order
        return missing,list(dict.fromkeys(expand))
