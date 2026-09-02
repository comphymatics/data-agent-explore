from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from dataclasses import replace
from pathlib import Path
from typing import Any

from enterprise_data_context.models import ContextFragment, Evidence as FragmentEvidence
from enterprise_data_context.template_input import load_template_inputs
from evaluation.benchmark.io import write_json, write_jsonl


CONTEXT_ENTITY_TYPES = {
    "scenario": "scenario",
    "topic": "other",
    "analysis-purpose": "scenario",
    "business-object": "business_object",
    "metric": "metric",
    "dimension": "dimension",
    "logical-model": "logical_model",
    "physical-model": "physical_model",
    "unknown": "other",
}
TARGET_ENTITY_TYPES = {
    "scenario": "scenario",
    "topic": "other",
    "analysis-purpose": "scenario",
    "business-object": "business_object",
    "metric": "metric",
    "dimension": "dimension",
    "logical-model": "logical_model",
    "physical-model": "physical_model",
    "table": "table",
    "field": "field",
    "grain": "grain",
    "processing-rule": "processing_rule",
    "environment-asset": "environment_asset",
}
SOURCE_TYPE_MAP = {
    "presales_usecases": "application_scenario",
    "kpi_definition": "metric_definition",
    "data_dictionary": "data_dictionary",
    "asset_catalog": "asset_catalog",
    "modeling_documents": "model_design",
    "sid_standard": "other",
}
DEFAULT_AUTHORITY = {
    "metric_definition": 1,
    "data_dictionary": 2,
    "model_design": 2,
    "asset_catalog": 3,
    "application_scenario": 3,
    "other": 9,
}
FIELD_NAME_KEYS = ("column_name", "field_name", "name")
SAFE_RE = re.compile(r"[^a-z0-9._-]+")


def _stable_entity(entity_type: str, name: str, namespace: str = "") -> dict[str, str]:
    normalized_type = TARGET_ENTITY_TYPES.get(entity_type, entity_type.replace("-", "_"))
    if normalized_type not in set(TARGET_ENTITY_TYPES.values()):
        normalized_type = "other"
    normalized = SAFE_RE.sub("-", name.lower()).strip("-.")
    suffix = normalized[:48] if normalized else hashlib.sha256(name.encode("utf-8")).hexdigest()[:16]
    namespace_hash = hashlib.sha256(namespace.encode("utf-8")).hexdigest()[:8] if namespace else ""
    entity_id = f"{normalized_type}:{namespace_hash + '-' if namespace_hash else ''}{suffix}"
    return {"entity_id": entity_id, "entity_type": normalized_type, "name": name}


def _source_type(fragment: ContextFragment) -> str:
    return SOURCE_TYPE_MAP.get(fragment.source_type, "other")


def _location(evidence: FragmentEvidence) -> dict[str, Any]:
    source = evidence.source
    return {
        key: value
        for key, value in {
            "sheet": source.sheet,
            "section": source.section,
            "table": source.table,
            "row": source.row,
            "column": source.column,
            "cell": source.cell,
        }.items()
        if value is not None
    }


def _scalar(value: Any) -> dict[str, Any]:
    return {"value": value, "value_type": type(value).__name__}


def _statement_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _make_record(
    fragment: ContextFragment,
    evidence: FragmentEvidence,
    subject: dict[str, str],
    predicate: str,
    obj: dict[str, Any],
    statement: str,
    source_versions: dict[str, str],
    authority: dict[str, int],
) -> dict[str, Any]:
    source_type = _source_type(fragment)
    excerpt = statement
    object_key = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    raw_id = "\x1f".join(
        (
            evidence.source.source_id,
            str(evidence.source.section or ""),
            fragment.fragment_id,
            subject["entity_id"],
            predicate,
            object_key,
        )
    )
    evidence_id = "ev-auto-" + hashlib.sha256(raw_id.encode("utf-8")).hexdigest()[:20]
    assertion_status = fragment.status if fragment.status in {"EXPLICIT", "DERIVED", "INFERRED", "CANDIDATE"} else "CANDIDATE"
    if assertion_status == "DERIVED":
        assertion_status = "CANDIDATE"
    return {
        "evidence_id": evidence_id,
        "assertion_status": assertion_status,
        "statement": statement,
        "subject": subject,
        "predicate": predicate,
        "object": obj,
        "source": {
            "source_id": evidence.source.source_id,
            "source_version": source_versions.get(evidence.source.source_id, "unversioned"),
            "source_type": source_type,
            "logical_uri": f"template://{evidence.source.source_id}",
            "authority_level": int(authority.get(source_type, DEFAULT_AUTHORITY[source_type])),
            "location": _location(evidence),
        },
        "excerpt": excerpt,
        "content_hash": hashlib.sha256(excerpt.encode("utf-8")).hexdigest(),
        "derived_from": [],
        "confidence": float(fragment.confidence),
        "review_status": "DRAFT",
        "reviewer_ids": [],
        "tags": ["auto-generated-from-template", fragment.section_type],
    }


def _first_evidence(fragment: ContextFragment) -> FragmentEvidence:
    if not fragment.evidence:
        raise ValueError(f"fragment has no Evidence: {fragment.fragment_id}")
    return fragment.evidence[0]


def _child_evidence(evidence: FragmentEvidence, child_pointer: str) -> FragmentEvidence:
    base = str(evidence.source.section or "").rstrip("/")
    return FragmentEvidence(
        source=replace(evidence.source, section=f"{base}/{child_pointer}"),
        note=evidence.note,
    )


def _field_records(
    fragment: ContextFragment,
    subject: dict[str, str],
    source_versions: dict[str, str],
    authority: dict[str, int],
) -> list[dict[str, Any]]:
    values = fragment.payload if isinstance(fragment.payload, list) else [fragment.payload]
    result: list[dict[str, Any]] = []
    evidence = _first_evidence(fragment)
    for index, value in enumerate(values):
        if fragment.section_type == "attributes":
            child_pointer = f"attributes/{index}"
        elif fragment.source_type == "data_dictionary":
            child_pointer = f"columns/{index}"
        else:
            child_pointer = "field" if len(values) == 1 else f"fields/{index}"
        item_evidence = _child_evidence(evidence, child_pointer)
        if isinstance(value, dict):
            field_name = next((str(value.get(key)).strip() for key in FIELD_NAME_KEYS if value.get(key)), "")
            if not field_name:
                result.append(
                    _make_record(
                        fragment, item_evidence, subject, f"has_{fragment.section_type}", _scalar(value),
                        f"{subject['name']} 的 {fragment.section_type} 为 {_statement_value(value)}",
                        source_versions, authority,
                    )
                )
                continue
            field = _stable_entity("field", field_name, subject["entity_id"])
            result.append(
                _make_record(
                    fragment, item_evidence, subject, "has_field", field,
                    f"{subject['name']} 包含字段 {field_name}", source_versions, authority,
                )
            )
            for key, item in sorted(value.items()):
                if key in FIELD_NAME_KEYS or item in (None, "", [], {}):
                    continue
                result.append(
                    _make_record(
                        fragment,
                        _child_evidence(item_evidence, key),
                        field,
                        f"field_{key}",
                        _scalar(item),
                        f"字段 {field_name} 的 {key} 为 {_statement_value(item)}",
                        source_versions, authority,
                    )
                )
        elif value not in (None, ""):
            field = _stable_entity("field", str(value), subject["entity_id"])
            result.append(
                _make_record(
                    fragment, item_evidence, subject, "has_field", field,
                    f"{subject['name']} 包含字段 {value}", source_versions, authority,
                )
            )
    return result


def _section_records(
    fragment: ContextFragment,
    subject: dict[str, str],
    source_versions: dict[str, str],
    authority: dict[str, int],
) -> list[dict[str, Any]]:
    if fragment.section_type in {"important_fields", "attributes"}:
        return _field_records(fragment, subject, source_versions, authority)
    evidence = _first_evidence(fragment)
    entity_sections = {
        "grain": ("has_grain", "grain"),
        "lineage.upstream": ("upstream_model", "physical-model"),
        "physical_models": ("provided_by", "physical-model"),
        "source_table": ("represented_by", "physical-model"),
    }
    if fragment.section_type in entity_sections:
        predicate, target_type = entity_sections[fragment.section_type]
        values = fragment.payload if isinstance(fragment.payload, list) else [fragment.payload]
        return [
            _make_record(
                fragment,
                evidence,
                subject,
                predicate,
                _stable_entity(target_type, str(value)),
                f"{subject['name']} 的 {fragment.section_type} 为 {value}",
                source_versions,
                authority,
            )
            for value in values
            if value not in (None, "")
        ]
    predicate_map = {
        "summary": "has_description",
        "formula": "has_formula",
        "processing_logic": "has_processing_rule",
        "data_type": "has_data_type",
        "storage": "has_storage",
    }
    predicate = predicate_map.get(fragment.section_type, f"has_{fragment.section_type}")
    values = fragment.payload if isinstance(fragment.payload, list) else [fragment.payload]
    return [
        _make_record(
            fragment,
            evidence,
            subject,
            predicate,
            _scalar(value),
            f"{subject['name']} 的 {fragment.section_type} 为 {_statement_value(value)}",
            source_versions,
            authority,
        )
        for value in values
        if value not in (None, "", [], {})
    ]


def fragments_to_evidence_candidates(
    fragments: list[ContextFragment],
    source_versions: dict[str, str],
    authority: dict[str, int] | None = None,
) -> list[dict[str, Any]]:
    authority = {**DEFAULT_AUTHORITY, **(authority or {})}
    result: list[dict[str, Any]] = []
    for fragment in fragments:
        if fragment.section_type == "identity":
            continue
        subject_type = CONTEXT_ENTITY_TYPES.get(fragment.context_type, "other")
        subject = _stable_entity(subject_type, fragment.candidate_name)
        if fragment.section_type == "references":
            fallback_evidence = _first_evidence(fragment)
            for reference in fragment.references:
                target_type = reference.target_type or "other"
                target = _stable_entity(target_type, reference.raw_target)
                evidence = reference.evidence[0] if reference.evidence else fallback_evidence
                result.append(
                    _make_record(
                        fragment,
                        evidence,
                        subject,
                        reference.relation,
                        target,
                        f"{fragment.candidate_name} {reference.relation} {reference.raw_target}",
                        source_versions,
                        authority,
                    )
                )
            continue
        result.extend(_section_records(fragment, subject, source_versions, authority))

    by_id: dict[str, dict[str, Any]] = {}
    for record in result:
        existing = by_id.get(record["evidence_id"])
        if existing and existing != record:
            raise ValueError(f"Evidence ID collision: {record['evidence_id']}")
        by_id.setdefault(record["evidence_id"], record)
    return sorted(by_id.values(), key=lambda record: record["evidence_id"])


def generate_evidence_candidates(
    template_dir: Path,
    output_dir: Path,
    *,
    authority: dict[str, int] | None = None,
) -> dict[str, Any]:
    batch = load_template_inputs(template_dir)
    source_versions = {
        source["id"]: f"sha256:{source['fingerprint'][:16]}" for source in batch["sources"]
    }
    records = fragments_to_evidence_candidates(batch["fragments"], source_versions, authority)
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError(f"output directory must be empty: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(output_dir / "evidence-candidates.jsonl", records)
    report = {
        "format": "enterprise-context-evidence-construction-report/v1",
        "template_files": [
            {**item, "path": Path(item["path"]).name} for item in batch["files"]
        ],
        "fragment_count": len(batch["fragments"]),
        "evidence_candidate_count": len(records),
        "counts_by_source_type": dict(sorted(Counter(r["source"]["source_type"] for r in records).items())),
        "counts_by_assertion_status": dict(sorted(Counter(r["assertion_status"] for r in records).items())),
        "review_status": "ALL_DRAFT",
        "promotion_blockers": [
            "verify source authority and version",
            "split or merge records where semantic atomicity is wrong",
            "resolve aliases and duplicate entities",
            "approve with real reviewer identities before Gold construction",
        ],
    }
    write_json(output_dir / "evidence-construction-report.json", report)
    return report
