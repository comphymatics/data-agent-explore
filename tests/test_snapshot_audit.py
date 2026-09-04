from enterprise_data_context.audit import audit_compiled_snapshot
from enterprise_data_context.compiler import ContextCompiler
from enterprise_data_context.models import ContextFragment, Evidence, SourceLocation, TypedReference


def evidence(source_id):
    return [Evidence(SourceLocation(source_id, f"/{source_id}.json", section="/0"))]


def test_snapshot_audit_checks_thresholds_and_candidate_isolation():
    fragments = [
        ContextFragment(
            "scenario", "scenario", "Railway", "identity", {"name": "Railway"},
            evidence=evidence("app"), source_type="presales",
        ),
        ContextFragment(
            "role", "scenario", "Railway", "semantic_role", "app-feature",
            evidence=evidence("app"), source_type="presales",
        ),
        ContextFragment(
            "metric", "metric", "RSRP", "identity", {"name": "RSRP"},
            evidence=evidence("kpi"), source_type="kpi",
        ),
        ContextFragment(
            "candidate", "scenario", "Railway", "references", {},
            references=[TypedReference(
                "uses_metric", "RSRP", target_type="metric", status="CANDIDATE",
                evidence=evidence("llm"),
            )],
            evidence=evidence("llm"), source_type="llm", status="CANDIDATE",
        ),
    ]
    compiled = ContextCompiler().compile_fragments(fragments)
    report = audit_compiled_snapshot(compiled)
    assert report["status"] == "PASSED"
    assert report["gates"]["candidate_references_isolated"] is True

    strict = audit_compiled_snapshot(
        compiled,
        require_delivery_manifest=True,
        require_complete_coverage=True,
        min_cross_source_confirmed=1,
        max_orphan_ratio=0.0,
    )
    assert strict["status"] == "FAILED"
    assert strict["gates"]["delivery_manifest_requirement_met"] is False
    assert strict["gates"]["coverage_requirement_met"] is False
    assert strict["gates"]["cross_source_confirmed_requirement_met"] is False
