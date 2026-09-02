from __future__ import annotations

from functools import lru_cache
from importlib import resources
import json
import re
from typing import Any

from .models import Evidence, SourceLocation


CATALOG_RESOURCE = "modeling-classification-v3.1.json"
CONTROLLED_LAYERS = {"SDL", "ODI"}


@lru_cache(maxsize=1)
def load_classification_catalog() -> dict[str, Any]:
    text = resources.files("enterprise_data_context.catalogs").joinpath(CATALOG_RESOURCE).read_text(encoding="utf-8")
    return json.loads(text)


def normalize_layer(value: Any) -> dict[str, Any]:
    raw = _clean(value)
    if not raw:
        return _result(raw, None, "MISSING")
    catalog = load_classification_catalog()
    for code, row in catalog["layers"].items():
        if _matches(raw, row.get("aliases", [])):
            approximate = _matches(raw, row.get("approximate_aliases", []))
            status = "APPROXIMATE_ALIAS" if approximate else ("EXACT" if _norm(raw) == _norm(code) else "ALIAS")
            return _result(raw, code, status, name=row["name"], policy=row["domain_policy"])
    return _result(raw, None, "UNRESOLVED")


def normalize_domain(layer: str | None, value: Any) -> dict[str, Any]:
    raw = _clean(value)
    if not raw:
        return _result(raw, None, "MISSING")
    if layer not in CONTROLLED_LAYERS:
        return _result(raw, raw, "UNCONTROLLED")
    for name, row in load_classification_catalog().get("domains", {}).get(layer, {}).items():
        if _matches(raw, row.get("aliases", []) + [name]):
            status = "EXACT" if _norm(raw) == _norm(name) else "ALIAS"
            return _result(raw, name, status, code=row.get("code"), english=row.get("english"))
    return _result(raw, None, "UNRESOLVED")


def normalize_topic(layer: str | None, domain: str | None, value: Any) -> dict[str, Any]:
    raw = _clean(value)
    if not raw:
        return _result(raw, None, "MISSING")
    if layer not in CONTROLLED_LAYERS:
        return _result(raw, raw, "UNCONTROLLED")
    domain_row = load_classification_catalog().get("domains", {}).get(layer, {}).get(domain or "")
    if not domain_row:
        return _result(raw, None, "UNRESOLVED")
    for topic in domain_row.get("topics", []):
        if _norm(raw) == _norm(topic):
            return _result(raw, topic, "EXACT")
    for alias, topic in domain_row.get("topic_aliases", {}).items():
        if _norm(raw) == _norm(alias):
            return _result(raw, topic, "ALIAS")
    return _result(raw, None, "UNRESOLVED")


def classify_model(layer_value: Any, domain_value: Any = None, topic_value: Any = None) -> dict[str, Any]:
    catalog = load_classification_catalog()
    layer = normalize_layer(layer_value)
    domain = normalize_domain(layer["canonical"], domain_value)
    topic = normalize_topic(layer["canonical"], domain["canonical"], topic_value)
    issues: list[dict[str, Any]] = []

    if layer["status"] == "MISSING":
        issues.append(_issue("missing_model_layer", "模型缺少正式分层"))
    elif layer["status"] == "UNRESOLVED":
        issues.append(_issue("unknown_model_layer", f"无法识别模型分层: {layer['raw']}"))

    canonical_layer = layer["canonical"]
    if canonical_layer in CONTROLLED_LAYERS:
        if domain["status"] == "MISSING":
            issues.append(_issue("missing_topic_domain", f"{canonical_layer} 模型缺少主题域"))
        elif domain["status"] == "UNRESOLVED":
            issues.append(_issue("unknown_topic_domain", f"{canonical_layer} 不包含主题域: {domain['raw']}"))

        if topic["status"] == "MISSING":
            issues.append(_issue("missing_model_topic", f"{canonical_layer} 模型缺少主题"))
        elif domain["canonical"]:
            domain_row = catalog["domains"][canonical_layer][domain["canonical"]]
            if topic["status"] == "UNRESOLVED" and domain_row.get("catalog_status") == "PARTIAL":
                issues.append(_issue("topic_catalog_incomplete", f"{domain['canonical']}域主题目录不完整，需人工复核: {topic['raw']}"))
            elif topic["status"] == "UNRESOLVED":
                issues.append(_issue("topic_not_in_domain", f"主题 {topic['raw']} 不属于 {domain['canonical']}域"))
        elif topic["status"] == "UNRESOLVED" and topic["raw"]:
            issues.append(_issue("topic_domain_unresolved", f"主题域未对齐，无法验证主题: {topic['raw']}"))

    aliases_used = any(row["status"] in {"ALIAS", "APPROXIMATE_ALIAS"} for row in (layer, domain, topic))
    if issues:
        status = "REVIEW"
    elif aliases_used:
        status = "NORMALIZED"
    else:
        status = "VALID"
    return {
        "taxonomy_version": catalog["catalog_version"],
        "layer": layer,
        "topic_domain": domain,
        "topic": topic,
        "status": status,
        "issues": issues,
    }


def classification_scope(query: str) -> dict[str, str]:
    """Extract only explicit governed layer/domain/topic terms from a query."""
    catalog = load_classification_catalog()
    layer = _find_alias(query, {
        code: row.get("aliases", []) for code, row in catalog["layers"].items()
    })
    layer_code = layer[0] if layer else None

    domain_candidates = catalog.get("domains", {}).get(layer_code, {}) if layer_code in CONTROLLED_LAYERS else {}
    if not domain_candidates:
        domain_candidates = {
            f"{candidate_layer}:{name}": row
            for candidate_layer, domains in catalog.get("domains", {}).items()
            for name, row in domains.items()
        }
    domain_match = _find_alias(query, {
        key: row.get("aliases", []) + [key.split(":", 1)[-1]] for key, row in domain_candidates.items()
    })
    domain_name = domain_match[0].split(":", 1)[-1] if domain_match else None
    if domain_match and ":" in domain_match[0] and not layer_code:
        layer_code = domain_match[0].split(":", 1)[0]

    topic_matches = []
    layers = [layer_code] if layer_code in CONTROLLED_LAYERS else list(catalog.get("domains", {}))
    for candidate_layer in layers:
        for candidate_domain, row in catalog["domains"].get(candidate_layer, {}).items():
            aliases = {topic: [topic] for topic in row.get("topics", [])}
            for alias, topic in row.get("topic_aliases", {}).items():
                aliases.setdefault(topic, [topic]).append(alias)
            match = _find_alias(query, aliases)
            if match:
                topic_matches.append((len(match[1]), candidate_layer, candidate_domain, match[0]))
    if topic_matches:
        _, topic_layer, topic_domain, topic_name = max(topic_matches)
        if not layer_code:
            layer_code = topic_layer
        if not domain_name:
            domain_name = topic_domain
    else:
        topic_name = None

    scope = {}
    if layer_code:
        scope["layer"] = layer_code
    if domain_name:
        scope["topic_domain"] = domain_name
    if topic_name and (not domain_name or topic_domain == domain_name):
        scope["topic"] = topic_name
    return scope


def validate_classification_sections(sections: dict[str, Any]) -> list[dict[str, Any]]:
    result = classify_model(
        sections.get("classification.layer_raw") or sections.get("classification.layer"),
        sections.get("classification.topic_domain_raw") or sections.get("topic_domain"),
        sections.get("classification.topic_raw") or sections.get("topic"),
    )
    return result["issues"]


def normalize_context_classification(ctx):
    """Normalize model classification regardless of which producer created the fragments."""
    if ctx.context_type not in {"physical-model", "logical-model"}:
        return ctx
    raw_sections = {
        "classification.layer": "classification.layer_raw",
        "topic_domain": "classification.topic_domain_raw",
        "topic": "classification.topic_raw",
    }
    raw_values = {}
    for formal, raw_section in raw_sections.items():
        raw = ctx.sections.get(raw_section)
        if raw in (None, ""):
            raw = ctx.sections.get(formal)
            if raw not in (None, ""):
                ctx.sections[raw_section] = raw
                ctx.section_status[raw_section] = ctx.section_status.get(formal, "EXPLICIT")
                ctx.evidence[raw_section] = list(ctx.evidence.get(formal, []))
        raw_values[formal] = raw

    result = classify_model(
        raw_values["classification.layer"], raw_values["topic_domain"], raw_values["topic"]
    )
    standard_evidence = _standard_evidence()
    classification_evidence = []
    for raw_section in raw_sections.values():
        _extend_unique_evidence(classification_evidence, ctx.evidence.get(raw_section, []))
    _extend_unique_evidence(classification_evidence, standard_evidence)
    for formal, row in (
        ("classification.layer", result["layer"]),
        ("topic_domain", result["topic_domain"]),
        ("topic", result["topic"]),
    ):
        raw = row["raw"]
        canonical = row["canonical"]
        if canonical:
            ctx.sections[formal] = canonical
            if row["status"] in {"ALIAS", "APPROXIMATE_ALIAS"}:
                ctx.section_status[formal] = "DERIVED"
                _extend_unique_evidence(ctx.evidence.setdefault(formal, []), standard_evidence)
        elif raw:
            ctx.sections.pop(formal, None)
            ctx.section_status.pop(formal, None)
            candidate_evidence = list(ctx.evidence.get(raw_sections[formal], []))
            _extend_unique_evidence(candidate_evidence, standard_evidence)
            _add_classification_candidate(ctx, formal, raw, candidate_evidence)

    ctx.sections["classification.taxonomy_version"] = result["taxonomy_version"]
    ctx.sections["classification.status"] = result["status"]
    ctx.section_status["classification.taxonomy_version"] = "DERIVED"
    ctx.section_status["classification.status"] = "DERIVED"
    ctx.evidence["classification.taxonomy_version"] = list(standard_evidence)
    ctx.evidence["classification.status"] = list(classification_evidence)
    if result["issues"]:
        ctx.sections["classification.issues"] = result["issues"]
        ctx.section_status["classification.issues"] = "DERIVED"
        ctx.evidence["classification.issues"] = list(classification_evidence)
    else:
        ctx.sections.pop("classification.issues", None)
        ctx.section_status.pop("classification.issues", None)
        ctx.evidence.pop("classification.issues", None)
    return ctx


def _find_alias(query: str, values: dict[str, list[str]]):
    matches = []
    for canonical, aliases in values.items():
        for alias in aliases:
            if _contains(query, alias):
                matches.append((canonical, alias))
    return max(matches, key=lambda row: len(row[1])) if matches else None


def _contains(text: str, value: str) -> bool:
    if not value:
        return False
    if re.fullmatch(r"[A-Za-z0-9 /_-]+", value):
        return re.search(rf"(?<![A-Za-z0-9]){re.escape(value)}(?![A-Za-z0-9])", text, re.I) is not None
    return value.casefold() in text.casefold()


def _matches(raw: str, aliases: list[str]) -> bool:
    value = _norm(raw)
    return any(value == _norm(alias) for alias in aliases)


def _norm(value: Any) -> str:
    return re.sub(r"[\s_\-:/（）()]+", "", str(value or "").strip().casefold())


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _result(raw, canonical, status, **extra):
    return {"raw": raw, "canonical": canonical, "status": status, **extra}


def _issue(code, message, severity="warning"):
    return {"severity": severity, "code": code, "message": message}


def _standard_evidence():
    return [Evidence(
        SourceLocation(
            source_id="modeling-standard:3.1",
            path="source-materials/数据模型设计和开发规范3.1.md",
            section="模型分层分域规范 / 统一命名规范",
        ),
        note="modeling-classification-3.1 governed normalization",
    )]


def _extend_unique_evidence(target, incoming):
    known = {
        (item.source.source_id, item.source.path, item.source.section, item.note)
        for item in target
    }
    for item in incoming:
        key = (item.source.source_id, item.source.path, item.source.section, item.note)
        if key not in known:
            known.add(key)
            target.append(item)


def _add_classification_candidate(ctx, section, payload, evidence):
    candidates = ctx.candidate_sections.setdefault(section, [])
    if any(item.get("payload") == payload for item in candidates):
        return
    candidates.append({
        "payload": payload,
        "status": "CANDIDATE",
        "confidence": 1.0,
        "source_type": "modeling_classification",
        "evidence": [
            {
                "source_id": item.source.source_id,
                "path": item.source.path,
                "sheet": item.source.sheet,
                "section": item.source.section,
                "table": item.source.table,
                "row": item.source.row,
                "column": item.source.column,
                "cell": item.source.cell,
                "note": item.note,
            }
            for item in evidence
        ],
    })
