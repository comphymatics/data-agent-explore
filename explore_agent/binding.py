from __future__ import annotations

import re
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
}


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
        }
        for hit in reference_hits
    ]
    reference_only_assets: list[dict[str, Any]] = []
    if result.state is AvailabilityState.NOT_FOUND_CONFIRMED:
        for item in reference_semantics:
            if item["type"] in ENVIRONMENT_BACKED_TYPES:
                reference_only_assets.append({
                    **item,
                    "assertion_status": "CANDIDATE",
                    "availability_state": AvailabilityState.NOT_FOUND_CONFIRMED.value,
                    "candidate_reason": "environment_absence_confirmed",
                })

    derived_bindings = _exact_bindings(result.assets, reference_semantics)
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
        "environment_facts": result.assets,
        "reference_semantics": reference_semantics,
        "confirmed_bindings": [],
        "derived_bindings": derived_bindings,
        "candidate_bindings": [],
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
                "assertion_status": "DERIVED",
                "knowledge_layer": "BINDING",
                "rule": "exact_normalized_name_or_code/v1",
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
