from __future__ import annotations

from pathlib import Path
import json

from .models import ContextFragment, Evidence, SourceLocation, TypedReference

VALID_STATUSES = {"EXPLICIT", "DERIVED", "INFERRED", "CANDIDATE"}


def fragment_from_mapping(data):
    """Deserialize one internal/legacy ContextFragment compatibility record."""
    required = ("fragment_id", "context_type", "candidate_name", "section_type", "payload")
    missing = [key for key in required if key not in data]
    if missing:
        raise ValueError(f"fragment missing required fields: {', '.join(missing)}")
    status = data.get("status", "EXPLICIT")
    if status not in VALID_STATUSES:
        raise ValueError(f"invalid fragment status: {status}")
    confidence = float(data.get("confidence", 1.0))
    if not 0.0 <= confidence <= 1.0:
        raise ValueError("fragment confidence must be between 0 and 1")
    evidence = [_evidence_from_mapping(x) for x in data.get("evidence", [])]
    if not evidence:
        raise ValueError("fragment must contain at least one evidence location")
    references = [_reference_from_mapping(x) for x in data.get("references", [])]
    return ContextFragment(
        fragment_id=str(data["fragment_id"]),
        context_type=data["context_type"],
        candidate_name=str(data["candidate_name"]),
        section_type=str(data["section_type"]),
        payload=data["payload"],
        aliases=list(data.get("aliases", [])),
        identity_hints=dict(data.get("identity_hints", {})),
        features=dict(data.get("features", {})),
        references=references,
        evidence=evidence,
        source_type=str(data.get("source_type", "unknown")),
        confidence=confidence,
        status=status,
    )


def load_fragments(path):
    """Load a legacy/internal JSON or JSONL ContextFragment batch."""
    path = Path(path)
    if path.suffix.lower() == ".jsonl":
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    else:
        payload = json.loads(path.read_text(encoding="utf-8"))
        rows = payload.get("fragments", []) if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise ValueError("fragment handoff must be a JSON array or an object with fragments")
    return [fragment_from_mapping(row) for row in rows]


def _evidence_from_mapping(data):
    source = data.get("source") or {}
    if not source.get("source_id") or not source.get("path"):
        raise ValueError("evidence.source requires source_id and path")
    return Evidence(source=SourceLocation(**source), note=data.get("note"))


def _reference_from_mapping(data):
    if not data.get("relation") or not data.get("raw_target"):
        raise ValueError("reference requires relation and raw_target")
    row = dict(data)
    row["evidence"] = [_evidence_from_mapping(x) for x in row.get("evidence", [])]
    return TypedReference(**row)
