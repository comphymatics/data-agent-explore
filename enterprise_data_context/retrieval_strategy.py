"""Single intent/scope/anchor policy for Explore and the four-tool serving API."""
import re
from .hierarchy_contracts import VIEWS, ROUTING_VERSION

INTENT_VIEWS = {
    **dict.fromkeys(("analysis_data_requirement", "scenario_exploration", "purpose_to_data", "metric_requirement"), "analysis"),
    **dict.fromkeys(("model_understanding", "business_semantic_understanding", "model_classification", "business_object_exploration", "topic_exploration"), "domain"),
    **dict.fromkeys(("asset_discovery", "model_inventory", "field_discovery", "layer_exploration", "physical_asset_exploration"), "asset"),
}
STRONG_TYPES = {"metric", "dimension", "logical-model", "physical-model", "field", "stable-id"}


def validate_strategy(value):
    if not isinstance(value, dict) or set(value) != {"mode", "hierarchy_views", "primary_view", "confidence", "reasons"}:
        raise ValueError("invalid retrieval_strategy contract")
    views = value["hierarchy_views"]
    if (value["mode"] not in {"direct", "hierarchical", "hybrid"} or not isinstance(views, list) or
        len(views) > 2 or len(set(views)) != len(views) or any(v not in VIEWS for v in views) or
        value["primary_view"] != (views[0] if views else None) or
        (value["mode"] == "direct") != (not views)):
        raise ValueError("invalid retrieval_strategy mode/views")
    if (type(value["confidence"]) not in (int, float) or not 0 <= value["confidence"] <= 1 or
        not isinstance(value["reasons"], list) or not value["reasons"] or
        not all(isinstance(r, str) and r for r in value["reasons"])):
        raise ValueError("invalid retrieval_strategy confidence/reasons")
    return value


def query_anchor_types(query):
    """Provisional identifiers; serving replaces these with verified index matches."""
    tokens = re.findall(r"[A-Z][A-Z0-9_]{2,}", query)
    return ["physical-model" if "_" in t else "metric" for t in tokens
            if t not in {"LTE", "NR", "IMS", "EPC", "ODS", "SDL", "ODI", "ADS", "DWD", "DWS"}]


def strategy(query, intent=None, scope=None, anchor_types=None, aspects=None, mode="auto", hierarchy=None, preferred=None):
    if mode not in {"auto", "direct", "hierarchical", "hybrid"} or hierarchy is not None and hierarchy not in VIEWS:
        raise ValueError("invalid retrieval mode or hierarchy view")
    if preferred is not None:
        validate_strategy(preferred)
    q = query.casefold(); scope = scope or {}; aspects = aspects or []
    anchors = sorted(set(anchor_types or []) & STRONG_TYPES)
    cross = any(w in q for w in ("还需要", "还能", "跨域", "结合", "what else", "across domains", "additional data"))
    if "cross_domain" in aspects or "complementary_data" in aspects:
        cross = True
    selected = ("hybrid" if anchors and cross else "direct" if anchors else "hierarchical") if mode == "auto" else mode
    reasons = (["exact_" + kind.replace("-", "_") + "_anchor" for kind in anchors] +
               (["cross_semantic_expansion"] if cross else []))
    views = []
    # Explicit governed layer/scope is stronger than legacy metric_to_models intent.
    if scope.get("layer") or scope.get("classification.layer") or re.search(r"\b(ods|sdl|odi|ads|dwd|dws)\b", q) or "数仓" in q or "分层" in q:
        views.append("asset"); reasons.append("asset_layer_scope")
    elif intent in INTENT_VIEWS:
        views.append(INTENT_VIEWS[intent]); reasons.append("intent:" + intent)
    elif preferred and preferred["hierarchy_views"]:
        views.extend(preferred["hierarchy_views"]); reasons.append("structured_router_views")
    elif any(w in q for w in ("主题", "业务对象", "domain", "topic", "网络资源配置", "归到")):
        views.append("domain"); reasons.append("business_semantic_scope")
    elif any(w in q for w in ("资产", "模型清单", "asset inventory")):
        views.append("asset"); reasons.append("asset_discovery_scope")
    else:
        views.append("analysis"); reasons.append("broad_analysis_question")
    if cross and any(w in q for w in ("分析", "覆盖", "场景", "指标")):
        views = ["analysis", *views]
    if scope.get("topic") or scope.get("topic_domain") or "business_mapping" in aspects:
        views.append("domain")
    if "fields" in aspects and not anchors:
        views.append("asset")
    if hierarchy:
        views = [hierarchy]; reasons.append("explicit_view_override")
    views = list(dict.fromkeys(views))[:2] if selected != "direct" else []
    if mode != "auto":
        reasons.append("explicit_mode_override")
    return validate_strategy({"mode": selected, "hierarchy_views": views,
        "primary_view": views[0] if views else None, "confidence": .99 if anchors else .95 if hierarchy or intent in INTENT_VIEWS or scope.get("layer") else .75,
        "reasons": list(dict.fromkeys(reasons)) or ["direct_override"]})


STRATEGY_SCHEMA = {'$schema': 'https://json-schema.org/draft/2020-12/schema',
 'title': 'Retrieval strategy',
 'type': 'object',
 'additionalProperties': False,
 'required': ['mode', 'hierarchy_views', 'primary_view', 'confidence', 'reasons'],
 'properties': {'mode': {'enum': ['direct', 'hierarchical', 'hybrid']},
                'hierarchy_views': {'type': 'array',
                                    'maxItems': 2,
                                    'uniqueItems': True,
                                    'items': {'enum': ['analysis', 'domain', 'asset']}},
                'primary_view': {'enum': ['analysis', 'domain', 'asset', None]},
                'confidence': {'type': 'number', 'minimum': 0, 'maximum': 1},
                'reasons': {'type': 'array',
                            'minItems': 1,
                            'items': {'type': 'string', 'minLength': 1}}}}
