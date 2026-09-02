from __future__ import annotations

import statistics
from collections import defaultdict
from typing import Any, Iterable

from .models import CaseScore, RetrievalResult


def deduplicate(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def score_result(
    result: RetrievalResult,
    case: dict[str, Any],
    known_evidence_ids: set[str],
) -> CaseScore:
    returned = deduplicate(result.evidence_ids)
    required = set(case.get("required_evidence", []))
    allowed = set(case.get("allowed_relevant_evidence", []))
    forbidden = set(case.get("forbidden_evidence", []))
    relevant = required | allowed

    matched_required = sorted(required & set(returned))
    matched_allowed = sorted(allowed & set(returned))
    returned_forbidden = sorted(forbidden & set(returned))
    returned_unknown = sorted(set(returned) - known_evidence_ids)

    if not result.valid:
        recall = None if case.get("negative") else 0.0
        precision = 0.0
    else:
        recall = None if case.get("negative") else len(matched_required) / len(required)
        if not returned:
            precision = 1.0 if case.get("negative") else 0.0
        else:
            precision = len(relevant & set(returned)) / len(returned)

    return CaseScore(
        system=result.system,
        case_id=result.case_id,
        query_id=result.query_id,
        repeat=result.repeat,
        evidence_recall=recall,
        evidence_precision=precision,
        query_tokens=result.query_tokens,
        token_complete=bool(result.token_details.get("complete", False)),
        matched_required=matched_required,
        matched_allowed=matched_allowed,
        returned_forbidden=returned_forbidden,
        returned_unknown=returned_unknown,
        valid=result.valid,
        error=result.error,
    )


def aggregate_scores(scores: Iterable[CaseScore]) -> dict[str, Any]:
    by_system: dict[str, list[CaseScore]] = defaultdict(list)
    for score in scores:
        by_system[score.system].append(score)

    summary: dict[str, Any] = {}
    for system, rows in sorted(by_system.items()):
        recalls = [row.evidence_recall for row in rows if row.evidence_recall is not None]
        precisions = [row.evidence_precision for row in rows]
        tokens = [row.query_tokens for row in rows if row.query_tokens is not None]
        summary[system] = {
            "runs": len(rows),
            "valid_runs": sum(1 for row in rows if row.valid),
            "evidence_recall_macro": statistics.fmean(recalls) if recalls else None,
            "evidence_precision_macro": statistics.fmean(precisions) if precisions else None,
            "query_tokens_mean": statistics.fmean(tokens) if tokens else None,
            "query_tokens_median": statistics.median(tokens) if tokens else None,
            "token_complete_runs": sum(1 for row in rows if row.token_complete),
            "forbidden_returns": sum(len(row.returned_forbidden) for row in rows),
            "unknown_returns": sum(len(row.returned_unknown) for row in rows),
        }
    return summary
