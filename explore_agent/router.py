import re

from enterprise_data_context.classification import classification_scope

KNOWN_TECH = ["LTE","5G","NR","VoLTE","VoNR","IMS","EPC"]

class QueryRouter:
    def __init__(self, provider=None, limits=None):
        from .bounded import BoundedInference
        self.semantic = BoundedInference(provider, limits)

    def analyze(self, query):
        from .planner import REQUIREMENTS
        from enterprise_data_context.retrieval_strategy import INTENT_VIEWS
        allowed_intents = list(dict.fromkeys([*REQUIREMENTS, *INTENT_VIEWS]))
        from .coverage import ASPECTS
        baseline = {"scope": self.route(query), "intent": self.intent(query), "entities": [], "aspects": []}
        if baseline["intent"]=="metric_to_models":
            baseline["entities"]=list(dict.fromkeys(x for x in re.findall(r"\b[A-Z][A-Z0-9_]{2,}\b",query) if x not in set(KNOWN_TECH)|{"ODS","SDL","ODI","ADS","DWD","DWS"}))[:8]
        def validate(value):
            if baseline["intent"] != "generic" and value.get("intent") != baseline["intent"]:
                raise ValueError("semantic route cannot remove explicit intent requirements")
            if set(value) != {"intent", "entities", "aspects"} or value["intent"] not in allowed_intents:
                raise ValueError("unsupported semantic route")
            if baseline["intent"]=="generic" and value["intent"]!="generic":
                hints={
                    "metric_to_models": ("模型","model","table","source","提供"),
                    "analysis_data_requirement": ("分析","analysis","数据","data","need","requirement"),
                    "model_understanding": ("字段","field","grain","粒度","业务对象","business object","model","模型"),
                    "impact_analysis": ("影响","impact","下游","downstream","lineage","血缘"),
                }
                if not any(hint in query.casefold() for hint in hints.get(value["intent"], {"analysis": ("分析", "体验", "移动", "场景", "analysis", "experience", "数据"), "domain": ("业务", "主题", "资源", "归类", "domain", "business"), "asset": ("模型", "字段", "层", "清单", "asset", "model", "field")}.get(INTENT_VIEWS.get(value["intent"]), ()))):
                    raise ValueError("intent upgrade has no query evidence")
            if not isinstance(value["entities"], list) or len(value["entities"]) > 8 or not all(
                isinstance(entity, str) and entity and entity in query for entity in value["entities"]):
                raise ValueError("ungrounded entity")
            if not isinstance(value["aspects"], list) or len(value["aspects"]) > 8 or not all(a in ASPECTS for a in value["aspects"]):
                raise ValueError("unsupported requirement aspect")
            return value
        proposed = self.semantic.invoke("route", {"query": query, "allowed_intents": allowed_intents, "allowed_aspects": sorted(ASPECTS)}, validate)
        if proposed:
            baseline.update(proposed)
        from enterprise_data_context.retrieval_strategy import strategy, query_anchor_types
        baseline["retrieval_strategy"] = strategy(query, baseline["intent"], baseline["scope"],
            query_anchor_types(query), baseline["aspects"])
        return baseline

    def route(self,query):
        q=query.lower(); scope=classification_scope(query)
        # Taxonomy aliases can suggest facets, but a business phrase does not
        # request a hard model filter. Retain only explicitly requested scopes.
        if not re.search(r"(?<![a-z0-9_])(ods|sdl|odi|ads|dwd|dws)(?![a-z0-9_])", q):
            scope.pop("layer", None)
        if "layer" not in scope and not any(word in q for word in ("主题", "domain", "topic")):
            scope.pop("topic_domain", None); scope.pop("topic", None)
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
