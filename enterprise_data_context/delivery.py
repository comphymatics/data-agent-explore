from __future__ import annotations

from collections import Counter
from importlib import resources
from pathlib import Path
import json

from jsonschema import Draft202012Validator

from .template_input import TemplateInputError, load_template_inputs


MANIFEST_NAME = "delivery-manifest.json"
DEFAULT_COVERAGE = {
    "status": "PARTIAL",
    "scope": "template-input",
    "reason": "No authoritative delivery inventory declared completeness.",
}


def validate_template_delivery(path: str | Path) -> dict:
    """Validate a parser Template JSON batch and its optional authoritative inventory."""
    root = Path(path)
    batch = load_template_inputs(root)
    manifest_path = root / MANIFEST_NAME if root.is_dir() else None
    manifest = _load_manifest(manifest_path) if manifest_path and manifest_path.exists() else None

    actual_files = _actual_files(root, batch)
    coverage = dict(DEFAULT_COVERAGE)
    checks = {
        "template_schema_valid": True,
        "fragments_non_empty": bool(batch["fragments"]),
        "evidence_complete": all(fragment.evidence for fragment in batch["fragments"]),
        "inventory_declared": manifest is not None,
        "inventory_exact": False,
        "fingerprints_match": False,
    }
    batch_id = None

    if manifest is not None:
        _verify_manifest_inventory(root, manifest, actual_files)
        declared = manifest["coverage_declaration"]
        if declared["status"] == "COMPLETE" and not declared["inventory_authoritative"]:
            raise TemplateInputError(
                "COMPLETE coverage requires coverage_declaration.inventory_authoritative=true"
            )
        coverage = {
            "status": declared["status"],
            "scope": declared["scope"],
            "reason": declared["reason"],
        }
        batch_id = manifest["batch_id"]
        checks["inventory_exact"] = True
        checks["fingerprints_match"] = True

    kinds = Counter(row["kind"] for row in actual_files)
    report = {
        "schema_version": "1.0",
        "status": "PASSED",
        "batch_id": batch_id,
        "manifest_present": manifest is not None,
        "coverage_declaration": coverage,
        "counts": {
            "files": len(actual_files),
            "fragments": len(batch["fragments"]),
            "kinds": dict(sorted(kinds.items())),
        },
        "checks": checks,
        "files": actual_files,
    }
    _report_validator().validate(report)
    return {
        **batch,
        "coverage_declaration": coverage,
        "delivery_manifest": manifest,
        "delivery_report": report,
    }


def _load_manifest(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TemplateInputError(f"invalid delivery manifest {path}: {exc}") from exc
    validator = _manifest_validator()
    errors = sorted(validator.iter_errors(payload), key=lambda error: list(error.absolute_path))
    if errors:
        error = errors[0]
        location = "/" + "/".join(str(part) for part in error.absolute_path)
        raise TemplateInputError(
            f"delivery manifest schema validation failed at {location} in {path}: {error.message}"
        )
    return payload


def _manifest_validator() -> Draft202012Validator:
    schema = json.loads(
        resources.files("contracts")
        .joinpath("template-delivery-manifest.schema.json")
        .read_text(encoding="utf-8")
    )
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _report_validator() -> Draft202012Validator:
    schema = json.loads(
        resources.files("contracts")
        .joinpath("template-delivery-report.schema.json")
        .read_text(encoding="utf-8")
    )
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _actual_files(root: Path, batch: dict) -> list[dict]:
    root_resolved = root.resolve() if root.is_dir() else root.parent.resolve()
    sources = {Path(row["path"]).resolve(): row for row in batch["sources"]}
    rows = []
    for row in batch["files"]:
        path = Path(row["path"]).resolve()
        source = sources[path]
        rows.append({
            "path": path.relative_to(root_resolved).as_posix(),
            "kind": row["kind"],
            "sha256": source["fingerprint"],
            "fragment_count": row["fragment_count"],
        })
    return sorted(rows, key=lambda row: row["path"])


def _verify_manifest_inventory(root: Path, manifest: dict, actual_files: list[dict]) -> None:
    root_resolved = root.resolve()
    declared_by_path = {}
    for row in manifest["files"]:
        relative = Path(row["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise TemplateInputError(f"delivery manifest path must stay inside the batch: {row['path']}")
        resolved = (root_resolved / relative).resolve()
        try:
            resolved.relative_to(root_resolved)
        except ValueError as exc:
            raise TemplateInputError(
                f"delivery manifest path must stay inside the batch: {row['path']}"
            ) from exc
        key = relative.as_posix()
        if key in declared_by_path:
            raise TemplateInputError(f"duplicate delivery manifest file entry: {key}")
        declared_by_path[key] = row

    actual_by_path = {row["path"]: row for row in actual_files}
    if set(declared_by_path) != set(actual_by_path):
        missing = sorted(set(actual_by_path) - set(declared_by_path))
        extra = sorted(set(declared_by_path) - set(actual_by_path))
        raise TemplateInputError(
            f"delivery manifest inventory mismatch; missing={missing}, extra={extra}"
        )
    for path, actual in actual_by_path.items():
        declared = declared_by_path[path]
        if declared["kind"] != actual["kind"]:
            raise TemplateInputError(
                f"delivery manifest kind mismatch for {path}: "
                f"declared={declared['kind']}, actual={actual['kind']}"
            )
        if declared["sha256"] != actual["sha256"]:
            raise TemplateInputError(f"delivery manifest fingerprint mismatch for {path}")
