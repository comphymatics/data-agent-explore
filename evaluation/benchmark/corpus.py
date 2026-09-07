# LEGACY / NON-HEADLINE EVALUATION — official entry: python -m evaluation
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .io import read_jsonl, write_json


SAFE_COMPONENT_RE = re.compile(r"[^a-zA-Z0-9._-]+")


def safe_component(value: str) -> str:
    cleaned = SAFE_COMPONENT_RE.sub("-", value).strip("-.")
    return cleaned or "unknown"


def render_evidence_page(record: dict[str, Any]) -> str:
    subject = record.get("subject", {})
    obj = record.get("object", {})
    source = record.get("source", {})
    location = source.get("location", {})
    derived_from = record.get("derived_from", [])
    tags = record.get("tags", [])
    return "\n".join(
        [
            f"# {record['evidence_id']}",
            "",
            f"EVIDENCE_ID: {record['evidence_id']}",
            f"ASSERTION_STATUS: {record['assertion_status']}",
            f"REVIEW_STATUS: {record['review_status']}",
            "",
            "## Fact",
            record["statement"],
            "",
            "## Semantic relation",
            f"SUBJECT: {json.dumps(subject, ensure_ascii=False, sort_keys=True)}",
            f"PREDICATE: {record['predicate']}",
            f"OBJECT: {json.dumps(obj, ensure_ascii=False, sort_keys=True)}",
            "",
            "## Evidence",
            f"EXCERPT: {record['excerpt']}",
            f"SOURCE_ID: {source['source_id']}",
            f"SOURCE_VERSION: {source['source_version']}",
            f"SOURCE_TYPE: {source['source_type']}",
            f"LOGICAL_URI: {source['logical_uri']}",
            f"LOCATION: {json.dumps(location, ensure_ascii=False, sort_keys=True)}",
            f"DERIVED_FROM: {json.dumps(derived_from, ensure_ascii=False)}",
            f"TAGS: {json.dumps(tags, ensure_ascii=False)}",
            "",
        ]
    )


def materialize_corpus(dataset_dir: Path, output_dir: Path) -> dict[str, Any]:
    dataset_dir = dataset_dir.resolve()
    output_dir = output_dir.resolve()
    evidence_path = dataset_dir / "evidence.jsonl"
    records = read_jsonl(evidence_path)
    if not records:
        raise ValueError(f"no Evidence records found in {evidence_path}")

    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError(f"output directory must be empty: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)

    files: list[dict[str, Any]] = []
    seen: set[str] = set()
    for record in sorted(records, key=lambda item: item["evidence_id"]):
        evidence_id = str(record["evidence_id"])
        if evidence_id in seen:
            raise ValueError(f"duplicate evidence_id: {evidence_id}")
        seen.add(evidence_id)
        source_id = safe_component(str(record["source"]["source_id"]))
        relative_path = Path("evidence-pages") / source_id / f"{safe_component(evidence_id)}.md"
        page = render_evidence_page(record)
        target = output_dir / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(page, encoding="utf-8")
        files.append(
            {
                "evidence_id": evidence_id,
                "path": relative_path.as_posix(),
                "sha256": hashlib.sha256(page.encode("utf-8")).hexdigest(),
            }
        )

    dataset_manifest_path = dataset_dir / "dataset-manifest.json"
    dataset_manifest = json.loads(dataset_manifest_path.read_text(encoding="utf-8"))
    corpus_manifest = {
        "format": "enterprise-context-evidence-corpus/v1",
        "dataset_id": dataset_manifest.get("dataset_id"),
        "dataset_version": dataset_manifest.get("version"),
        "record_count": len(files),
        "files": files,
        "gold_fields_included": False,
    }
    write_json(output_dir / "corpus-manifest.json", corpus_manifest)
    (output_dir / "README.txt").write_text(
        "Evaluation-only neutral Evidence corpus. Gold cases and design oracles are not included.\n",
        encoding="utf-8",
    )
    return corpus_manifest
