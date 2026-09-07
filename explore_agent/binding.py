from __future__ import annotations

import re
from collections import Counter
from typing import Any

from enterprise_data_context.environment import (
    AvailabilityState,
    EnvironmentBindingResult,
)


ENVIRONMENT_FIRST_INTENTS = {
    "metric_to_models",
    "analysis_data_requirement",
    "model_understanding",
    "impact_analysis",
}

ENVIRONMENT_HINTS = (
    "当前环境",
    "客户环境",
    "当前客户",
    "现网",
    "已有模型",
    "可用模型",
    "available model",
    "current environment",
)

ENVIRONMENT_BACKED_TYPES = {
    "metric",
    "dimension",
    "measure",
    "logical-model",
    "physical-model",
    "field",
    "business-attribute",
}


def snapshot_evidence(result, evidence):
    caps = result.capabilities
    return bool(caps and caps.environment_id and caps.snapshot_token and evidence and
                all(isinstance(e,dict) and e.get("environment_id")==caps.environment_id and
                    e.get("snapshot_token")==caps.snapshot_token for e in evidence))


def identity_rule(asset, reference, result):
    """Exact typed identities only. Names and physical-name hints are never keys."""
    if (asset.get("type")!=reference["type"] or asset.get("assertion_status")!="EXPLICIT" or
        not snapshot_evidence(result,asset.get("evidence"))):
        return None
    attrs=asset.get("attributes",{})
    if attrs.get("reference_path")==reference["path"]:
        return "provider_explicit_crosswalk/v3"
    identity=reference.get("binding_identity") or {}
    keys=identity.get("keys",{})
    if identity.get("status")!="EXPLICIT" or not identity.get("evidence"):
        return None
    if (not keys.get("identity_namespace") or keys.get("identity_namespace")!=attrs.get("identity_namespace") or
        keys.get("environment_id")!=result.capabilities.environment_id):
        return None
    for key in ("stable_id","strong_key"):
        if isinstance(keys.get(key),str) and keys[key].strip() and keys[key]==attrs.get(key):
            if key=="strong_key" and not re.fullmatch(r"[^.\s]+\.[^.\s]+(?:\.[^.\s]+)*",keys[key]):
                continue
            return "same_type_scoped_"+key+"/v3"
    return None


def environment_required(intent: str, query: str) -> bool:
    lowered = query.lower()
    return intent in ENVIRONMENT_FIRST_INTENTS or any(hint in lowered for hint in ENVIRONMENT_HINTS)


def build_binding_overlay(
    result: EnvironmentBindingResult,
    reference_hits: list[dict[str, Any]],
    *,
    reference_index_version: str | None,
    required_coverage: list[str] | tuple[str, ...],
) -> dict[str, Any]:
    reference_semantics = [
        {
            "path": hit["path"],
            "type": hit["context_type"],
            "name": hit["name"],
            "relevance": hit.get("score", 0.0),
            "knowledge_layer": "REFERENCE",
            "assertion_status": "EXPLICIT",
            "reference_index_version": reference_index_version,
            "binding_identity": hit.get("binding_identity"),
        }
        for hit in reference_hits
    ]
    # Identity needs an explicit provider crosswalk, matching type and environment snapshot.
    identity_bindings = []
    candidate_bindings = _exact_bindings(result.assets, reference_semantics)
    for asset in result.assets:
        for reference in reference_semantics:
            rule=identity_rule(asset,reference,result)
            if rule:
                identity_bindings.append({
                    "environment_asset_id": asset["id"], "reference_path": reference["path"],
                    "environment_type":asset["type"],"reference_type":reference["type"],
                    "binding_kind": "IDENTITY", "assertion_status": "EXPLICIT",
                    "environment_id": result.capabilities.environment_id,
                    "snapshot_token": result.capabilities.snapshot_token,
                    "reference_index_version": reference_index_version,
                    "evidence": asset["evidence"], "rule": rule,
                    "reference_evidence":(reference.get("binding_identity") or {}).get("evidence",[]),
                })
    counts=Counter(row["reference_path"] for row in identity_bindings)
    asset_counts=Counter(row["environment_asset_id"] for row in identity_bindings)
    for row in identity_bindings:
        if counts[row["reference_path"]]>1 or asset_counts[row["environment_asset_id"]]>1:
            candidate_bindings.append({**row,"assertion_status":"CANDIDATE","rule":"ambiguous_provider_crosswalk/v2"})
    identity_bindings=[row for row in identity_bindings if counts[row["reference_path"]]==1 and asset_counts[row["environment_asset_id"]]==1]
    bound = {row["reference_path"] for row in identity_bindings}
    candidate_bindings = [row for row in candidate_bindings if row["reference_path"] not in bound]
    reference_only_assets = [{**item, "availability_state": result.state.value,
                              "candidate_reason": "environment_absence_confirmed" if result.state is AvailabilityState.NOT_FOUND_CONFIRMED else "environment_identity_unverified"}
                             for item in reference_semantics if item["type"] in ENVIRONMENT_BACKED_TYPES and item["path"] not in bound]
    asset_ids = {asset["id"] for asset in result.assets}
    reference_paths = {item["path"] for item in reference_semantics}
    semantic_mappings = []
    structural_relations = []
    for relation in result.relations:
        if relation.get("assertion_status") != "EXPLICIT" or not snapshot_evidence(result,relation.get("evidence")):
            continue
        if not isinstance(relation.get("predicate"),str) or not relation["predicate"].strip():
            continue
        if relation.get("source_id") not in asset_ids:
            continue
        if relation.get("predicate") in {"MAPS_TO", "SEMANTIC_MAPPING"}:
            if relation.get("target_id") in reference_paths | asset_ids:
                semantic_mappings.append({**relation, "binding_kind": "SEMANTIC_MAPPING"})
        elif relation.get("target_id") in asset_ids:
            structural_relations.append({**relation, "binding_kind": "STRUCTURAL_RELATION"})
    missing = []
    if result.required:
        if result.state in {
            AvailabilityState.UNSUPPORTED,
            AvailabilityState.UNAVAILABLE,
            AvailabilityState.TRUNCATED,
        }:
            missing.append("environment_availability")
        elif result.state is AvailabilityState.NOT_FOUND_CONFIRMED:
            missing.append("environment_assets")
        elif result.state is AvailabilityState.PARTIAL:
            missing.extend(
                f"environment_coverage:{key}"
                for key in required_coverage
                if not result.coverage.get(key, False)
            )

    return {
        "binding_policy_version":"identity-binding/v3",
        "environment_facts": result.assets,
        "reference_semantics": reference_semantics,
        "confirmed_bindings": identity_bindings,
        "derived_bindings": [],
        "candidate_bindings": candidate_bindings,
        "identity_bindings": identity_bindings,
        "semantic_mappings": semantic_mappings,
        "structural_relations": structural_relations,
        "reference_only_assets": reference_only_assets,
        "conflicts": [],
        "missing_context": list(dict.fromkeys(missing)),
    }


def reference_only_candidates(overlay: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "path": item["path"],
            "section": "environment_binding",
            "payload": {
                "type": item["type"],
                "name": item["name"],
                "knowledge_layer": "REFERENCE",
                "availability_state": item["availability_state"],
            },
            "status": "CANDIDATE",
            "confidence": item.get("relevance", 0.0),
            "reason": item["candidate_reason"],
        }
        for item in overlay.get("reference_only_assets", [])
    ]


def _exact_bindings(
    environment_assets: list[dict[str, Any]],
    reference_semantics: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    bindings = []
    seen: set[tuple[str, str]] = set()
    for asset in environment_assets:
        environment_keys = {
            _normalize(asset.get("id")),
            _normalize(asset.get("code")),
            _normalize(asset.get("name")),
            *(_normalize(alias) for alias in asset.get("aliases", [])),
        } - {""}
        for reference in reference_semantics:
            if not _compatible_types(str(asset.get("type", "")), str(reference.get("type", ""))):
                continue
            reference_keys = {
                _normalize(reference.get("name")),
                _normalize(reference.get("path", "").rsplit("/", 1)[-1]),
            } - {""}
            if not (environment_keys & reference_keys):
                continue
            key = (str(asset["id"]), str(reference["path"]))
            if key in seen:
                continue
            seen.add(key)
            bindings.append({
                "environment_asset_id": asset["id"],
                "reference_path": reference["path"],
                "assertion_status": "CANDIDATE",
                "binding_kind": "SEMANTIC_MAPPING",
                "knowledge_layer": "BINDING",
                "rule": "name_or_code_candidate/v2",
                "evidence": {
                    "environment": asset.get("evidence", []),
                    "reference_index_version": reference.get("reference_index_version"),
                },
            })
    return bindings


def _compatible_types(environment_type: str, reference_type: str) -> bool:
    if environment_type == reference_type:
        return True
    groups = (
        {"metric", "measure"},
        {"logical-model", "physical-model"},
        {"field", "business-attribute"},
    )
    return any(environment_type in group and reference_type in group for group in groups)


def _normalize(value: Any) -> str:
    return re.sub(r"[\W_]+", "", str(value or "").lower(), flags=re.UNICODE)
