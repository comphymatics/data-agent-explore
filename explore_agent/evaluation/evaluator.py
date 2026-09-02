from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class EvaluationCase:
    case_id: str
    query: str
    expected_contexts: list[str] = field(default_factory=list)
    required_coverage: list[str] = field(default_factory=list)
    expected_missing: list[str] = field(default_factory=list)


@dataclass
class EvaluationReport:
    total: int
    passed: int
    context_recall: float
    coverage_accuracy: float
    cases: list[dict]


class GoldenGateError(ValueError):
    pass


def evaluate(agent, cases):
    """Evaluate Context Bundle behavior without treating golden data as production facts."""
    results=[]; recalled=0; expected_total=0; coverage_hits=0; coverage_total=0
    for case in cases:
        bundle=agent.explore(case.query)
        actual={x["path"] for x in bundle.primary_contexts}
        actual.update(x["name"] for x in bundle.primary_contexts)
        expected=set(case.expected_contexts)
        matched=expected & actual
        recalled += len(matched); expected_total += len(expected)

        required_ok={key:bool(bundle.coverage.get(key)) for key in case.required_coverage}
        missing_ok={key:key in bundle.missing_context for key in case.expected_missing}
        coverage_hits += sum(required_ok.values()) + sum(missing_ok.values())
        coverage_total += len(required_ok) + len(missing_ok)
        passed=(matched==expected and all(required_ok.values()) and all(missing_ok.values()))
        results.append({
            "case_id":case.case_id,
            "passed":passed,
            "matched_contexts":sorted(matched),
            "missing_expected_contexts":sorted(expected-matched),
            "required_coverage":required_ok,
            "expected_missing":missing_ok,
            "bundle_missing_context":list(bundle.missing_context),
        })

    return EvaluationReport(
        total=len(results),
        passed=sum(1 for x in results if x["passed"]),
        context_recall=recalled/expected_total if expected_total else 1.0,
        coverage_accuracy=coverage_hits/coverage_total if coverage_total else 1.0,
        cases=results,
    )


def assert_golden_gate(
    report,
    min_context_recall=1.0,
    min_coverage_accuracy=1.0,
):
    """Fail a staging/release job without promoting Golden data to production facts."""
    failed_cases=report.total-report.passed
    reasons=[]
    if failed_cases:
        reasons.append(f"{failed_cases} case(s) failed")
    if report.context_recall < min_context_recall:
        reasons.append(
            f"context_recall {report.context_recall:.3f} < {min_context_recall:.3f}"
        )
    if report.coverage_accuracy < min_coverage_accuracy:
        reasons.append(
            f"coverage_accuracy {report.coverage_accuracy:.3f} < {min_coverage_accuracy:.3f}"
        )
    if reasons:
        raise GoldenGateError("golden gate rejected release: " + "; ".join(reasons))
    return report
