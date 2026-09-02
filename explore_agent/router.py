import re

from enterprise_data_context.classification import classification_scope

KNOWN_TECH = ["LTE","5G","NR","VoLTE","VoNR","IMS","EPC"]

class QueryRouter:
    def route(self,query):
        q=query.lower(); scope=classification_scope(query)
        for t in KNOWN_TECH:
            if t.lower() in q: scope["technology"]=t; break
        if "地铁" in query or "metro" in q: scope["scenario"]="metro"
        if "弱覆盖" in query: scope["analysis_purpose"]="weak-coverage"
        metrics=[x for x in re.findall(r"\b[A-Z][A-Z0-9_]{2,}\b",query) if x not in {"ODS","SDL","ODI","ADS","DWD","DWS"}]
        if metrics: scope["symbol"]=metrics[0]
        return scope

    def intent(self,query):
        q=query.lower()
        if ("模型" in query or "model" in q) and ("提供" in query or "哪些" in query):
            return "metric_to_models"
        if "需要哪些数据" in query or "需要什么数据" in query:
            return "analysis_data_requirement"
        if "业务对象" in query or "粒度" in query or "字段" in query:
            return "model_understanding"
        if "影响" in query and ("下游" in query or "impact" in q):
            return "impact_analysis"
        return "generic"
