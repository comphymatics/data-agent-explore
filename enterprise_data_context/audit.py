from __future__ import annotations

from collections import Counter


def audit_compiled_snapshot(
    compiled: dict,
    *,
    require_delivery_manifest: bool = False,
    require_complete_coverage: bool = False,
    min_cross_source_confirmed: int = 0,
    max_unresolved_ratio: float = 1.0,
    max_orphan_ratio: float = 1.0,
) -> dict:
    if min_cross_source_confirmed < 0:
        raise ValueError("min_cross_source_confirmed must be non-negative")
    for name, value in (
        ("max_unresolved_ratio", max_unresolved_ratio),
        ("max_orphan_ratio", max_orphan_ratio),
    ):
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"{name} must be between 0 and 1")

    manifest = compiled.get("manifest", {})
    associations = compiled.get("association_report", {})
    coverage = compiled.get("coverage_declaration", {})
    delivery = compiled.get("delivery_report") or {}
    quality_issues = compiled.get("quality_issues", [])
    errors = [row for row in quality_issues if row.get("severity") == "error"]
    warnings = [row for row in quality_issues if row.get("severity") == "warning"]
    quality_codes = Counter(row.get("code", "unknown") for row in quality_issues)

    reference_status = associations.get("references_by_status", {})
    reference_count = int(associations.get("reference_count", 0))
    unresolved_count = int(reference_status.get("UNRESOLVED", 0))
    unresolved_ratio = unresolved_count / reference_count if reference_count else 0.0
    context_count = int(associations.get("context_count", len(compiled.get("contexts", []))))
    orphan_count = int(associations.get("orphan_context_count", 0))
    orphan_ratio = orphan_count / context_count if context_count else 0.0

    evidence_complete = all(fragment.evidence for fragment in compiled.get("fragments", []))
    candidate_isolated = _candidate_references_are_isolated(compiled)
    manifest_present = bool(delivery.get("manifest_present"))
    cross_source = int(associations.get("cross_source_confirmed_count", 0))

    gates = {
        "no_quality_errors": not errors,
        "fragment_evidence_complete": evidence_complete,
        "candidate_references_isolated": candidate_isolated,
        "delivery_manifest_requirement_met": (
            manifest_present or not require_delivery_manifest
        ),
        "coverage_requirement_met": (
            coverage.get("status") == "COMPLETE" or not require_complete_coverage
        ),
        "cross_source_confirmed_requirement_met": cross_source >= min_cross_source_confirmed,
        "unresolved_ratio_requirement_met": unresolved_ratio <= max_unresolved_ratio,
        "orphan_ratio_requirement_met": orphan_ratio <= max_orphan_ratio,
    }
    return {
        "schema_version": "1.0",
        "status": "PASSED" if all(gates.values()) else "FAILED",
        "index_version": compiled.get("index_version") or manifest.get("index_version"),
        "coverage_declaration": coverage,
        "delivery": {
            "batch_id": delivery.get("batch_id"),
            "manifest_present": manifest_present,
        },
        "policy": {
            "require_delivery_manifest": require_delivery_manifest,
            "require_complete_coverage": require_complete_coverage,
            "min_cross_source_confirmed": min_cross_source_confirmed,
            "max_unresolved_ratio": max_unresolved_ratio,
            "max_orphan_ratio": max_orphan_ratio,
        },
        "counts": manifest.get("counts", {}),
        "quality": {
            "error_count": len(errors),
            "warning_count": len(warnings),
            "by_code": dict(sorted(quality_codes.items())),
        },
        "associations": {
            "reference_count": reference_count,
            "references_by_status": reference_status,
            "cross_source_confirmed_count": cross_source,
            "orphan_context_count": orphan_count,
            "unresolved_ratio": round(unresolved_ratio, 6),
            "orphan_ratio": round(orphan_ratio, 6),
        },
        "gates": gates,
    }


def _candidate_references_are_isolated(compiled: dict) -> bool:
    candidate_edges = {
        (context.path, reference.relation, reference.target_path)
        for context in compiled.get("contexts", [])
        for reference in context.references
        if reference.status == "CANDIDATE" and reference.target_path
    }
    if not candidate_edges:
        return True
    graph_edges = {
        (edge["source"], edge["relation"], edge["target"])
        for edges in compiled["graph"].out.values()
        for edge in edges
    }
    backref_edges = {
        (row["source"], row["relation"], target)
        for target, rows in compiled.get("backrefs", {}).items()
        for row in rows
    }
    return not candidate_edges.intersection(graph_edges | backref_edges)
