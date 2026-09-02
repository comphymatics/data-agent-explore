from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .adapters import OpenCodeExploreAdapter, OpenVikingHTTPAdapter
from .adapters.base import RetrievalAdapter
from .io import append_jsonl, read_json, read_jsonl, write_json, write_jsonl
from .models import CaseScore, RetrievalResult
from .scoring import aggregate_scores, score_result


ADAPTERS: dict[str, type[RetrievalAdapter]] = {
    "opencode_explore": OpenCodeExploreAdapter,
    "openviking": OpenVikingHTTPAdapter,
}


def sanitize_config(value: Any, key: str = "") -> Any:
    lowered = key.lower()
    if any(term in lowered for term in ("password", "secret")):
        return "<redacted>"
    if ("token" in lowered or "api_key" in lowered) and not lowered.endswith("_env"):
        return "<redacted>"
    if isinstance(value, dict):
        return {item_key: sanitize_config(item, item_key) for item_key, item in value.items()}
    if isinstance(value, list):
        return [sanitize_config(item) for item in value]
    return value


def benchmark_fingerprint(
    dataset_manifest: dict[str, Any],
    corpus_manifest_text: str,
    config: dict[str, Any],
    systems: list[str],
    selected_case_ids: list[str],
    repeats: int,
    include_variants: bool,
) -> str:
    value = {
        "dataset_id": dataset_manifest.get("dataset_id"),
        "dataset_version": dataset_manifest.get("version"),
        "corpus_manifest_sha256": hashlib.sha256(corpus_manifest_text.encode("utf-8")).hexdigest(),
        "config": sanitize_config(config),
        "systems": systems,
        "selected_case_ids": selected_case_ids,
        "repeats": repeats,
        "include_variants": include_variants,
    }
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def iter_queries(case: dict[str, Any], include_variants: bool) -> Iterable[tuple[str, str]]:
    yield "base", case["query"]
    if include_variants:
        for index, query in enumerate(case.get("query_variants", []), start=1):
            yield f"variant-{index}", query


def _family_summary(scores: list[CaseScore], case_by_id: dict[str, dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    families = sorted({case_by_id[row.case_id]["scenario_family"] for row in scores})
    for family in families:
        rows = [row for row in scores if case_by_id[row.case_id]["scenario_family"] == family]
        result[family] = aggregate_scores(rows)
    return result


def _paired_deltas(summary: dict[str, Any]) -> dict[str, float | None]:
    left = summary.get("opencode_explore")
    right = summary.get("openviking")
    if not left or not right:
        return {}

    def delta(field: str) -> float | None:
        left_value = left.get(field)
        right_value = right.get(field)
        if left_value is None or right_value is None:
            return None
        return float(left_value) - float(right_value)

    return {
        "opencode_minus_openviking_recall": delta("evidence_recall_macro"),
        "opencode_minus_openviking_precision": delta("evidence_precision_macro"),
        "opencode_minus_openviking_mean_tokens": delta("query_tokens_mean"),
    }


def render_markdown(summary: dict[str, Any], preflight: dict[str, Any]) -> str:
    lines = [
        "# OpenCode Explore vs OpenViking",
        "",
        "Accuracy is macro-averaged over executed query/repeat rows. Invalid positive runs score "
        "zero recall and precision. Token values are comparable only when token-complete equals runs.",
        "",
        "| System | Runs | Valid | Recall | Precision | Mean query tokens | Token-complete |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for system, values in summary.get("overall", {}).items():
        recall = values.get("evidence_recall_macro")
        precision = values.get("evidence_precision_macro")
        tokens = values.get("query_tokens_mean")
        recall_text = f"{recall:.4f}" if recall is not None else "n/a"
        precision_text = f"{precision:.4f}" if precision is not None else "n/a"
        tokens_text = f"{tokens:.1f}" if tokens is not None else "n/a"
        lines.append(
            f"| {system} | {values['runs']} | {values['valid_runs']} | {recall_text} | "
            f"{precision_text} | {tokens_text} | {values['token_complete_runs']} |"
        )
    lines.extend(["", "## Preflight", ""])
    for system, value in preflight.items():
        status = "available" if value.get("available") else f"unavailable: {value.get('error')}"
        lines.append(f"- {system}: {status}")
    lines.append("")
    return "\n".join(lines)


def run_benchmark(
    *,
    dataset_dir: Path,
    corpus_dir: Path,
    config_path: Path,
    output_dir: Path,
    systems: list[str],
    repeats: int = 1,
    include_variants: bool = False,
    case_ids: set[str] | None = None,
    resume: bool = False,
    skip_unavailable: bool = False,
    preflight_only: bool = False,
) -> dict[str, Any]:
    dataset_dir = dataset_dir.resolve()
    corpus_dir = corpus_dir.resolve()
    output_dir = output_dir.resolve()
    config = read_json(config_path)
    dataset_manifest = read_json(dataset_dir / "dataset-manifest.json")
    corpus_manifest_path = corpus_dir / "corpus-manifest.json"
    corpus_manifest_text = corpus_manifest_path.read_text(encoding="utf-8")
    evidence = read_jsonl(dataset_dir / "evidence.jsonl")
    cases = [case for case in read_jsonl(dataset_dir / "cases.jsonl") if case["review_status"] == "APPROVED"]
    if case_ids:
        cases = [case for case in cases if case["case_id"] in case_ids]
        missing = sorted(case_ids - {case["case_id"] for case in cases})
        if missing:
            raise ValueError(f"requested case IDs were not found or not approved: {', '.join(missing)}")
    if not cases:
        raise ValueError("no approved evaluation cases selected")
    if repeats < 1:
        raise ValueError("repeats must be at least 1")
    unknown_systems = sorted(set(systems) - set(ADAPTERS))
    if unknown_systems:
        raise ValueError(f"unknown systems: {', '.join(unknown_systems)}")

    selected_case_ids = sorted(case["case_id"] for case in cases)
    fingerprint = benchmark_fingerprint(
        dataset_manifest,
        corpus_manifest_text,
        config,
        systems,
        selected_case_ids,
        repeats,
        include_variants,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "run-manifest.json"
    results_path = output_dir / "results.jsonl"
    if manifest_path.exists():
        if not resume:
            raise ValueError(f"output already contains a run; use --resume: {output_dir}")
        previous = read_json(manifest_path)
        if previous.get("fingerprint") != fingerprint:
            raise ValueError("resume fingerprint mismatch; use a new output directory")
    elif results_path.exists():
        raise ValueError("results.jsonl exists without run-manifest.json; use a new output directory")

    adapters: dict[str, RetrievalAdapter] = {}
    preflight: dict[str, Any] = {}
    retrieval_corpus_dir = corpus_dir / "evidence-pages"
    if not retrieval_corpus_dir.is_dir():
        raise ValueError(f"evidence-pages directory not found: {retrieval_corpus_dir}")
    for system in systems:
        system_config = config.get(system, {})
        if not system_config.get("enabled", True):
            preflight[system] = {"available": False, "error": "disabled in config"}
            continue
        adapter = ADAPTERS[system](system_config, retrieval_corpus_dir)
        try:
            details = adapter.preflight()
            preflight[system] = {"available": True, "details": details}
            adapters[system] = adapter
        except Exception as exc:
            preflight[system] = {"available": False, "error": str(exc)}
            if not skip_unavailable:
                raise RuntimeError(f"{system} preflight failed: {exc}") from exc

    run_manifest = {
        "format": "enterprise-context-comparison-run/v1",
        "fingerprint": fingerprint,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "dataset_id": dataset_manifest.get("dataset_id"),
        "dataset_version": dataset_manifest.get("version"),
        "systems": systems,
        "repeats": repeats,
        "include_variants": include_variants,
        "selected_case_ids": selected_case_ids,
        "config": sanitize_config(config),
        "preflight": preflight,
    }
    write_json(manifest_path, run_manifest)
    if preflight_only:
        return {"preflight": preflight, "output_dir": str(output_dir)}
    if not adapters:
        raise RuntimeError("no benchmark system is available after preflight")

    prior_rows = read_jsonl(results_path) if results_path.exists() else []
    completed_keys = {
        (row["system"], row["case_id"], row["query_id"], int(row["repeat"]))
        for row in prior_rows
    }
    total = sum(
        repeats * sum(1 for _ in iter_queries(case, include_variants))
        for case in cases
    ) * len(adapters)
    expected_systems = set(adapters)
    expected_cases = set(selected_case_ids)
    completed = sum(
        1 for system, case_id, _, _ in completed_keys
        if system in expected_systems and case_id in expected_cases
    )
    for system, adapter in adapters.items():
        for case in cases:
            for query_id, query in iter_queries(case, include_variants):
                for repeat in range(1, repeats + 1):
                    key = (system, case["case_id"], query_id, repeat)
                    if key in completed_keys:
                        continue
                    result = adapter.retrieve(case, query, query_id, repeat)
                    append_jsonl(results_path, [result.to_dict()])
                    completed_keys.add(key)
                    completed += 1
                    print(
                        f"[{completed}/{total}] {system} {case['case_id']} {query_id} "
                        f"repeat={repeat} valid={result.valid}"
                    )

    result_rows = [RetrievalResult(**row) for row in read_jsonl(results_path)]
    known_ids = {record["evidence_id"] for record in evidence}
    case_by_id = {case["case_id"]: case for case in cases}
    scores = [score_result(row, case_by_id[row.case_id], known_ids) for row in result_rows]
    write_jsonl(output_dir / "scores.jsonl", [row.to_dict() for row in scores])
    overall = aggregate_scores(scores)
    summary = {
        "overall": overall,
        "by_scenario_family": _family_summary(scores, case_by_id),
        "paired_deltas": _paired_deltas(overall),
        "preflight": preflight,
    }
    write_json(output_dir / "summary.json", summary)
    (output_dir / "summary.md").write_text(render_markdown(summary, preflight), encoding="utf-8")
    return summary
