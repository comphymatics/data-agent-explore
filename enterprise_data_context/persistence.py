from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import json

from .graph.backend import BackendGraph
from .indexes.element import ElementIndex
from .indexes.hierarchy import HierarchyIndex
from .indexes.page import PageIndex
from .models import (
    CanonicalContext,
    ContextFragment,
    ContextPage,
    DocumentElement,
    DocumentIR,
    Evidence,
    SourceLocation,
    TypedReference,
)
from .references.resolver import build_backrefs
from .organization import association_report

SCHEMA_VERSION = "1.3"


class QualityGateError(ValueError):
    pass


def assert_publishable(compiled):
    errors = [
        issue for issue in compiled.get("quality_issues", [])
        if issue.get("severity") == "error"
    ]
    if errors:
        codes = sorted({issue.get("code", "unknown") for issue in errors})
        raise QualityGateError(
            f"context snapshot has {len(errors)} quality error(s): {', '.join(codes)}"
        )
    return compiled


def save_compiled(compiled, out_dir):
    """Write an immutable version directory, then atomically move latest.json."""
    assert_publishable(compiled)
    hierarchy = compiled.get("hierarchy") or HierarchyIndex().project(compiled["contexts"])
    associations = compiled.get("association_report") or association_report(
        compiled["contexts"], hierarchy
    )
    inference_runs = list(compiled.get("inference_runs", []))
    coverage_declaration = dict(compiled.get("coverage_declaration") or {
        "status": "UNKNOWN",
        "scope": "unspecified",
        "reason": "No authoritative source inventory declared completeness.",
    })
    compiled["hierarchy"] = hierarchy
    compiled["association_report"] = associations
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    canonical_payload = {
        "contexts": [asdict(x) for x in compiled["contexts"]],
        "pages": [asdict(x) for x in compiled["pages"]],
        "source_fingerprints": compiled.get("source_fingerprints", {}),
        "coverage_declaration": coverage_declaration,
    }
    content_hash = sha256(
        json.dumps(canonical_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    index_version = f"context-{content_hash[:16]}"
    version_dir = out / "versions" / index_version

    if not version_dir.exists():
        version_dir.mkdir(parents=True, exist_ok=False)
        for sub in ("document-ir", "fragments", "contexts", "pages"):
            (version_dir / sub).mkdir()
        for document in compiled["documents"]:
            _write_json(version_dir / "document-ir" / f"{safe(document.source_id)}.json", asdict(document))
        for i, fragment in enumerate(compiled["fragments"]):
            _write_json(version_dir / "fragments" / f"{i:06d}.json", asdict(fragment))
        for context in compiled["contexts"]:
            _write_json(version_dir / "contexts" / f"{safe(context.canonical_id)}.json", asdict(context))
        for page in compiled["pages"]:
            _write_json(version_dir / "pages" / f"{safe(page.canonical_id)}.json", asdict(page))
        _write_json(version_dir / "quality.json", compiled["quality_issues"])
        _write_json(version_dir / "association-report.json", associations)
        if inference_runs:
            _write_json(version_dir / "inference-runs.json", inference_runs)

        manifest = {
            "schema_version": SCHEMA_VERSION,
            "index_version": index_version,
            "content_hash": content_hash,
            "built_at": datetime.now(timezone.utc).isoformat(),
            "source_fingerprints": compiled.get("source_fingerprints", {}),
            "coverage_declaration": coverage_declaration,
            "counts": {
                "documents": len(compiled["documents"]),
                "fragments": len(compiled["fragments"]),
                "contexts": len(compiled["contexts"]),
                "pages": len(compiled["pages"]),
                "quality_issues": len(compiled["quality_issues"]),
                "hierarchy_nodes": len(hierarchy.nodes),
                "hierarchy_edges": hierarchy.edge_count,
                "confirmed_references": associations.get("references_by_status", {}).get(
                    "CONFIRMED", 0
                ),
                "unresolved_references": associations.get("references_by_status", {}).get(
                    "UNRESOLVED", 0
                ),
                "candidate_references": associations.get("references_by_status", {}).get(
                    "CANDIDATE", 0
                ),
                "inference_runs": len(inference_runs),
            },
        }
        _write_json(version_dir / "manifest.json", manifest)
    else:
        manifest = _read_json(version_dir / "manifest.json")

    latest = {"index_version": index_version, "path": f"versions/{index_version}"}
    _write_json_atomic(out / "latest.json", latest)
    compiled["index_version"] = index_version
    compiled["manifest"] = manifest
    return manifest


def load_compiled(in_dir, index_version=None):
    """Load a saved snapshot and rebuild all disposable indexes and graph views."""
    root = Path(in_dir)
    snapshot = root
    if (root / "latest.json").exists() or index_version:
        if index_version:
            snapshot = root / "versions" / index_version
        else:
            latest = _read_json(root / "latest.json")
            snapshot = root / latest["path"]

    if not snapshot.exists():
        raise FileNotFoundError(f"context snapshot not found: {snapshot}")

    documents = [_document_from_dict(_read_json(p)) for p in _json_files(snapshot / "document-ir")]
    fragments = [_fragment_from_dict(_read_json(p)) for p in _json_files(snapshot / "fragments")]
    contexts = [_context_from_dict(_read_json(p)) for p in _json_files(snapshot / "contexts")]
    pages = [_page_from_dict(_read_json(p)) for p in _json_files(snapshot / "pages")]
    quality = _read_json(snapshot / "quality.json") if (snapshot / "quality.json").exists() else []
    saved_association = (
        _read_json(snapshot / "association-report.json")
        if (snapshot / "association-report.json").exists()
        else None
    )
    inference_runs = (
        _read_json(snapshot / "inference-runs.json")
        if (snapshot / "inference-runs.json").exists()
        else []
    )
    manifest = _read_json(snapshot / "manifest.json") if (snapshot / "manifest.json").exists() else {}

    page_index = PageIndex()
    element_index = ElementIndex()
    for page in pages:
        page_index.add(page)
        element_index.add(page)

    graph = BackendGraph().project(contexts)
    hierarchy = HierarchyIndex().project(contexts)
    for page in pages:
        if not page.hierarchy:
            page.hierarchy = hierarchy.describe(page.path)
    return {
        "documents": documents,
        "fragments": fragments,
        "contexts": contexts,
        "pages": pages,
        "page_index": page_index,
        "element_index": element_index,
        "graph": graph,
        "hierarchy": hierarchy,
        "association_report": saved_association or association_report(contexts, hierarchy),
        "inference_runs": inference_runs,
        "backrefs": build_backrefs(contexts),
        "quality_issues": quality,
        "source_fingerprints": manifest.get("source_fingerprints", {}),
        "coverage_declaration": manifest.get("coverage_declaration", {
            "status": "UNKNOWN", "scope": "unspecified",
            "reason": "Legacy snapshot without a coverage declaration.",
        }),
        "index_version": manifest.get("index_version", index_version),
        "manifest": manifest,
    }


def safe(value):
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in value)


def _json_files(directory):
    return sorted(directory.glob("*.json")) if directory.exists() else []


def _write_json(path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_json_atomic(path, payload):
    temporary = path.with_suffix(path.suffix + ".tmp")
    _write_json(temporary, payload)
    temporary.replace(path)


def _read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _location_from_dict(data):
    return SourceLocation(**data) if data else None


def _evidence_from_dict(data):
    return Evidence(source=_location_from_dict(data["source"]), note=data.get("note"))


def _reference_from_dict(data):
    row = dict(data)
    row["evidence"] = [_evidence_from_dict(x) for x in row.get("evidence", [])]
    return TypedReference(**row)


def _element_from_dict(data):
    row = dict(data)
    row["source"] = _location_from_dict(row.get("source"))
    return DocumentElement(**row)


def _document_from_dict(data):
    row = dict(data)
    row["elements"] = [_element_from_dict(x) for x in row.get("elements", [])]
    return DocumentIR(**row)


def _fragment_from_dict(data):
    row = dict(data)
    row["references"] = [_reference_from_dict(x) for x in row.get("references", [])]
    row["evidence"] = [_evidence_from_dict(x) for x in row.get("evidence", [])]
    return ContextFragment(**row)


def _context_from_dict(data):
    row = dict(data)
    row["references"] = [_reference_from_dict(x) for x in row.get("references", [])]
    row["evidence"] = {
        key: [_evidence_from_dict(x) for x in values]
        for key, values in row.get("evidence", {}).items()
    }
    return CanonicalContext(**row)


def _page_from_dict(data):
    return ContextPage(**data)
