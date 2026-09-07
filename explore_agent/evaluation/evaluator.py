from __future__ import annotations
from dataclasses import dataclass, field
from collections import defaultdict
from statistics import mean
import math


@dataclass
class EvaluationCase:
    case_id: str
    query: str
    expected_contexts: list[str] = field(default_factory=list)
    required_coverage: list[str] = field(default_factory=list)  # legacy reference-only projection
    expected_missing: list[str] = field(default_factory=list)
    expected_anchors: list[str] = field(default_factory=list)
    relevant_contexts: list[str] | None = None
    expected_coverage: dict[str, str] = field(default_factory=dict)  # layer|entity_name|aspect
    expected_bindings: list[list[str]] | None = None
    expected_elements: list[str | dict] = field(default_factory=list)
    anchor_k: int = 1
    explore_options: dict = field(default_factory=dict)
    max_tool_calls: int | None = None
    max_token_cost: int | None = None


@dataclass
class EvaluationReport:
    total: int
    passed: int
    context_recall: float
    coverage_accuracy: float | None
    cases: list[dict]
    anchor_recall: float | None = None
    bundle_recall: float | None = None
    bundle_precision: float | None = None
    binding_precision: float | None = None
    focused_expansion_success: float | None = None
    tool_calls: float | None = None
    token_cost: float | None = None
    metric_sample_counts: dict = field(default_factory=dict)
    anchor_recall_at_k: dict = field(default_factory=dict)
    efficiency: dict = field(default_factory=dict)


class GoldenGateError(ValueError):
    pass


def _ratio(numerator, denominator):
    return numerator/denominator if denominator else None


def evaluate(agent, cases, progress=None):
    """Closed-world retrieval oracles stay in evaluation; unscored metrics remain null."""
    results = []
    at_k = defaultdict(lambda: [0,0])
    totals = {key: [0, 0] for key in ("anchor_recall", "bundle_recall", "bundle_precision", "coverage_accuracy", "binding_precision", "focused_expansion_success")}
    for case in cases:
        bundle = agent.explore(case.query, **case.explore_options)
        hits = bundle.primary_contexts
        actual_paths = {x["path"] for x in hits}
        names = {x["path"]: x["name"] for x in hits}
        actual = actual_paths | set(names.values())
        expected = set(case.expected_contexts)
        matched = expected & actual
        if case.anchor_k < 1:
            raise ValueError("anchor_k must be positive")
        anchor_rows = bundle.serving.get("anchor_candidates", [])[:case.anchor_k]
        anchors = {r["path"] for r in anchor_rows}
        anchor_names = {r["name"] for r in anchor_rows}
        values = {"bundle_recall": (len(matched), len(expected))}
        if case.expected_anchors:
            values["anchor_recall"] = (len(set(case.expected_anchors) & (anchors | anchor_names)), len(set(case.expected_anchors)))
            at_k[str(case.anchor_k)][0] += values["anchor_recall"][0]
            at_k[str(case.anchor_k)][1] += values["anchor_recall"][1]
        if case.relevant_contexts is not None:
            relevant = set(case.relevant_contexts)
            values["bundle_precision"] = (sum(h["path"] in relevant or h["name"] in relevant for h in hits), len(hits))
        required_ok = {key: bundle.coverage_summary.get(key, False) for key in case.required_coverage}
        missing_ok = {key: key in bundle.missing_context for key in case.expected_missing}
        by_requirement = {r["id"]:r["status"] for r in bundle.coverage.values()}
        grouped=defaultdict(list)
        for row in bundle.coverage.values():
            key="|".join((row["layer"],row["entity_name"],row["aspect"]))
            grouped[key].append(row["status"])
            if row.get("selector"):
                by_requirement[key+"|"+row["selector"]]=row["status"]
        for key,states in grouped.items():
            by_requirement[key]=states[0] if len(set(states))==1 else "PARTIAL"
        statuses_ok = {key: by_requirement.get(key) == status for key, status in case.expected_coverage.items()}
        checks = [*required_ok.values(), *missing_ok.values(), *statuses_ok.values()]
        values["coverage_accuracy"] = (sum(checks), len(checks))
        binding_ok = True
        if case.expected_bindings is not None:
            expected_bindings = {tuple(pair) for pair in case.expected_bindings}
            actual_bindings = {(r["environment_asset_id"], r["reference_path"]) for r in bundle.binding_overlay.get("identity_bindings", [])}
            values["binding_precision"] = (len(actual_bindings & expected_bindings), len(actual_bindings))
            binding_ok = actual_bindings == expected_bindings
        expansion_ok = True
        if case.expected_elements:
            elements = [r for expanded in bundle.focused_expansion.values() for r in expanded.get("elements", [])]
            def element_matches(target, row):
                if not row.get("evidence") or row.get("status") not in {"EXPLICIT","DERIVED"}:
                    return False
                if isinstance(target,dict):
                    if row["path"]!=target["parent_path"] or row.get("kind")!=target["kind"]:
                        return False
                    target=target["identifier"]
                return target==row["element_id"] or target in row.get("identifiers",[])
            found = [any(element_matches(target,row) for row in elements) for target in case.expected_elements]
            expansion_ok = all(found)
            values["focused_expansion_success"] = (sum(found), len(found))
        metrics = {key: _ratio(*value) for key, value in values.items()}
        for key, (num, den) in values.items():
            totals[key][0] += num; totals[key][1] += den
        tool_calls = bundle.telemetry.get("total_tool_calls")
        token_cost = bundle.telemetry.get("total_tokens_estimated")
        cost_ok = ((case.max_tool_calls is None or tool_calls is not None and tool_calls <= case.max_tool_calls) and
                   (case.max_token_cost is None or token_cost is not None and token_cost <= case.max_token_cost))
        precision_ok = metrics.get("bundle_precision") in (None, 1.0)
        passed = (matched == expected and all(checks) and binding_ok and expansion_ok and cost_ok and precision_ok and metrics.get("anchor_recall") in (None, 1.0))
        results.append({"case_id": case.case_id, "passed": passed, "metrics": metrics,
                        "tool_calls": tool_calls, "token_cost": token_cost,
                        "matched_contexts": sorted(matched), "missing_expected_contexts": sorted(expected-matched),
                        "required_coverage": required_ok, "expected_missing": missing_ok, "coverage_checks": statuses_ok,
                        "bundle_missing_context": bundle.missing_context, "binding_ok": binding_ok,
                        "focused_expansion_ok": expansion_ok, "cost_ok": cost_ok,
                        "telemetry": bundle.telemetry})
        results[-1]["anchor_k"]=case.anchor_k
        results[-1]["anchor_candidates"]=anchor_rows
        if progress:
            progress(results[-1])
    ratios = {key: _ratio(*value) for key, value in totals.items()}
    return EvaluationReport(total=len(results), passed=sum(r["passed"] for r in results),
        context_recall=ratios["bundle_recall"] if ratios["bundle_recall"] is not None else 1.0,
        coverage_accuracy=ratios.pop("coverage_accuracy"),
        cases=results, **{k:v for k,v in ratios.items() if k != "coverage_accuracy"},
        tool_calls=mean(r["tool_calls"] for r in results) if results and all(r["tool_calls"] is not None for r in results) else None,
        token_cost=mean(r["token_cost"] for r in results) if results and all(r["token_cost"] is not None for r in results) else None,
        metric_sample_counts={key: den for key, (_, den) in totals.items()},
        anchor_recall_at_k={k:{"recall":_ratio(*v),"expected_anchors":v[1]} for k,v in at_k.items()},
        efficiency={"relevant_contexts_per_1000_tokens":_ratio(1000*totals["bundle_recall"][0],sum(r["token_cost"] or 0 for r in results))
                    if all(r["token_cost"] is not None for r in results) else None,
                    "relevant_contexts_per_tool_call":_ratio(totals["bundle_recall"][0],sum(r["tool_calls"] or 0 for r in results))
                    if all(r["tool_calls"] is not None for r in results) else None})


def assert_golden_gate(report, min_context_recall=1.0, min_coverage_accuracy=1.0, *,
                       minimums=None, maximums=None, baseline=None, max_regressions=None):
    reasons = []
    if not report.total:
        reasons.append("empty Golden suite")
    if report.passed < report.total:
        reasons.append(f"{report.total-report.passed} case(s) failed")
    for key, threshold in {"context_recall": min_context_recall, "coverage_accuracy": min_coverage_accuracy, **(minimums or {})}.items():
        value = getattr(report, key)
        if value is None or not math.isfinite(value) or value < threshold:
            reasons.append(f"{key} {value} below {threshold} or unscored")
    for key, threshold in (maximums or {}).items():
        value = getattr(report, key)
        if value is None or not math.isfinite(value) or value > threshold:
            reasons.append(f"{key} {value} exceeds {threshold} or unscored")
    if baseline:
        for key, tolerance in (max_regressions or {}).items():
            current, old = getattr(report, key), getattr(baseline, key)
            if current is None or old is None:
                reasons.append(f"{key} regression unscored")
            elif (current-old if key in {"tool_calls", "token_cost"} else old-current) > tolerance:
                reasons.append(f"{key} regressed beyond {tolerance}")
    if reasons:
        raise GoldenGateError("golden gate rejected release: "+"; ".join(reasons))
    return report
