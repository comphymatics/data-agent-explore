#!/usr/bin/env python3
"""Validate an enterprise-context evaluation dataset.

The validator intentionally checks more than JSON Schema: IDs must be unique,
Gold references must resolve, approved Gold cannot depend on candidates, and
model-design cases must have exactly one hidden design oracle.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[2]
CONTRACT_DIR = ROOT / "evaluation" / "contracts"
SCHEMA_PATHS = {
    "manifest": CONTRACT_DIR / "dataset-manifest.schema.json",
    "evidence": CONTRACT_DIR / "evidence-record.schema.json",
    "cases": CONTRACT_DIR / "evaluation-case.schema.json",
    "oracles": CONTRACT_DIR / "design-oracle.schema.json",
}

RESEARCH_SUBTYPES = {
    "single_layer",
    "adjacent_mapping",
    "multi_layer",
    "environment_gap_conflict",
}
DESIGN_SUBTYPES = {
    "schema_context",
    "processing_context",
    "full_design_context",
    "reuse_and_change",
    "insufficient_context",
}
EXPECTED_BUDGET = {"S": 2048, "M": 4096, "L": 8192}
GOLD_STATUSES = {"EXPLICIT", "DERIVED"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset-dir",
        type=Path,
        required=True,
        help="Directory containing dataset-manifest.json and JSONL files",
    )
    return parser.parse_args()


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"missing required file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path}:{exc.lineno}: {exc.msg}") from exc


def read_jsonl(path: Path) -> list[tuple[int, dict[str, Any]]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError as exc:
        raise ValueError(f"missing required file: {path}") from exc

    records: list[tuple[int, dict[str, Any]]] = []
    for line_number, raw in enumerate(lines, start=1):
        if not raw.strip():
            continue
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON in {path}:{line_number}: {exc.msg}") from exc
        if not isinstance(value, dict):
            raise ValueError(f"{path}:{line_number}: JSONL record must be an object")
        records.append((line_number, value))
    return records


def load_validator(path: Path) -> Draft202012Validator:
    schema = read_json(path)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


def schema_errors(
    label: str,
    records: Iterable[tuple[int | None, dict[str, Any]]],
    validator: Draft202012Validator,
) -> list[str]:
    errors: list[str] = []
    for line_number, record in records:
        for error in sorted(validator.iter_errors(record), key=lambda item: list(item.path)):
            location = ".".join(str(part) for part in error.absolute_path) or "<root>"
            line = f":{line_number}" if line_number is not None else ""
            errors.append(f"{label}{line} {location}: {error.message}")
    return errors


def duplicate_id_errors(records: list[dict[str, Any]], field: str, label: str) -> list[str]:
    counts = Counter(record.get(field) for record in records)
    return [f"duplicate {label}: {value}" for value, count in counts.items() if value and count > 1]


def all_case_evidence_ids(case: dict[str, Any]) -> set[str]:
    result = set(case.get("required_evidence", []))
    result.update(case.get("allowed_relevant_evidence", []))
    result.update(case.get("forbidden_evidence", []))
    for conflict in case.get("expected_conflicts", []):
        result.update(conflict.get("evidence_ids", []))
    return result


def oracle_evidence_ids(oracle: dict[str, Any]) -> set[str]:
    result: set[str] = set()
    for element in oracle.get("schema_elements", []):
        result.update(element.get("evidence_ids", []))
    for join in oracle.get("joins", []):
        result.update(join.get("evidence_ids", []))
    for step in oracle.get("processing_steps", []):
        result.update(step.get("evidence_ids", []))
    return result


def find_derived_cycle(evidence_by_id: dict[str, dict[str, Any]]) -> list[str] | None:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(evidence_id: str, path: list[str]) -> list[str] | None:
        if evidence_id in visiting:
            start = path.index(evidence_id)
            return path[start:] + [evidence_id]
        if evidence_id in visited:
            return None
        visiting.add(evidence_id)
        path.append(evidence_id)
        for parent in evidence_by_id[evidence_id].get("derived_from", []):
            if parent in evidence_by_id:
                cycle = visit(parent, path)
                if cycle:
                    return cycle
        path.pop()
        visiting.remove(evidence_id)
        visited.add(evidence_id)
        return None

    for evidence_id in evidence_by_id:
        cycle = visit(evidence_id, [])
        if cycle:
            return cycle
    return None


def semantic_errors(
    manifest: dict[str, Any],
    evidence: list[dict[str, Any]],
    cases: list[dict[str, Any]],
    oracles: list[dict[str, Any]],
) -> list[str]:
    errors: list[str] = []
    errors.extend(duplicate_id_errors(evidence, "evidence_id", "evidence_id"))
    errors.extend(duplicate_id_errors(cases, "case_id", "case_id"))
    errors.extend(duplicate_id_errors(oracles, "case_id", "oracle case_id"))

    evidence_by_id = {record["evidence_id"]: record for record in evidence if "evidence_id" in record}
    cases_by_id = {record["case_id"]: record for record in cases if "case_id" in record}
    oracles_by_case = {record["case_id"]: record for record in oracles if "case_id" in record}
    evidence_ids = set(evidence_by_id)

    for record in evidence:
        evidence_id = record.get("evidence_id", "<unknown>")
        for parent in record.get("derived_from", []):
            if parent not in evidence_ids:
                errors.append(f"{evidence_id}: derived_from references unknown evidence {parent}")
            elif parent == evidence_id:
                errors.append(f"{evidence_id}: derived_from cannot reference itself")

    cycle = find_derived_cycle(evidence_by_id)
    if cycle:
        errors.append(f"derived Evidence cycle: {' -> '.join(cycle)}")

    for case in cases:
        case_id = case.get("case_id", "<unknown>")
        required = set(case.get("required_evidence", []))
        allowed = set(case.get("allowed_relevant_evidence", []))
        forbidden = set(case.get("forbidden_evidence", []))

        overlaps = {
            "required/allowed": required & allowed,
            "required/forbidden": required & forbidden,
            "allowed/forbidden": allowed & forbidden,
        }
        for label, values in overlaps.items():
            if values:
                errors.append(f"{case_id}: {label} overlap: {sorted(values)}")

        missing = all_case_evidence_ids(case) - evidence_ids
        if missing:
            errors.append(f"{case_id}: unknown Evidence IDs: {sorted(missing)}")

        for evidence_id in required | allowed:
            record = evidence_by_id.get(evidence_id)
            if not record:
                continue
            if record.get("review_status") != "APPROVED":
                errors.append(f"{case_id}: Gold Evidence {evidence_id} is not APPROVED")
            if record.get("assertion_status") not in GOLD_STATUSES:
                errors.append(
                    f"{case_id}: Gold Evidence {evidence_id} has forbidden assertion_status "
                    f"{record.get('assertion_status')}"
                )

        family = case.get("scenario_family")
        subtype = case.get("subtype")
        if family == "requirement_research" and subtype not in RESEARCH_SUBTYPES:
            errors.append(f"{case_id}: subtype {subtype} is invalid for requirement_research")
        if family == "model_design_preparation" and subtype not in DESIGN_SUBTYPES:
            errors.append(f"{case_id}: subtype {subtype} is invalid for model_design_preparation")

        difficulty = case.get("difficulty")
        if difficulty in EXPECTED_BUDGET and case.get("context_token_budget") != EXPECTED_BUDGET[difficulty]:
            errors.append(
                f"{case_id}: difficulty {difficulty} requires context_token_budget "
                f"{EXPECTED_BUDGET[difficulty]}"
            )

        has_oracle = case_id in oracles_by_case
        if family == "model_design_preparation" and not has_oracle:
            errors.append(f"{case_id}: model-design case must have exactly one design oracle")
        if family == "requirement_research" and has_oracle:
            errors.append(f"{case_id}: requirement-research case must not have a design oracle")

    for oracle in oracles:
        case_id = oracle.get("case_id", "<unknown>")
        case = cases_by_id.get(case_id)
        if not case:
            errors.append(f"oracle {case_id}: references unknown case")
            continue
        if case.get("scenario_family") != "model_design_preparation":
            errors.append(f"oracle {case_id}: linked case is not model_design_preparation")
        missing = oracle_evidence_ids(oracle) - evidence_ids
        if missing:
            errors.append(f"oracle {case_id}: unknown Evidence IDs: {sorted(missing)}")

    if manifest.get("status") == "FROZEN" and not manifest.get("approved_by"):
        errors.append("FROZEN dataset must contain at least one approved_by identity")

    return errors


def print_summary(
    manifest: dict[str, Any],
    evidence: list[dict[str, Any]],
    cases: list[dict[str, Any]],
    oracles: list[dict[str, Any]],
) -> None:
    print(f"dataset: {manifest.get('dataset_id')}@{manifest.get('version')} ({manifest.get('status')})")
    print(f"evidence: {len(evidence)}")
    print(f"cases: {len(cases)}")
    print(f"design_oracles: {len(oracles)}")
    print("scenario_family: " + json.dumps(Counter(c.get("scenario_family") for c in cases), ensure_ascii=False, sort_keys=True))
    print("subtype: " + json.dumps(Counter(c.get("subtype") for c in cases), ensure_ascii=False, sort_keys=True))
    print("difficulty: " + json.dumps(Counter(c.get("difficulty") for c in cases), ensure_ascii=False, sort_keys=True))
    print("assertion_status: " + json.dumps(Counter(e.get("assertion_status") for e in evidence), ensure_ascii=False, sort_keys=True))
    print("review_status: " + json.dumps(Counter(e.get("review_status") for e in evidence), ensure_ascii=False, sort_keys=True))


def main() -> int:
    args = parse_args()
    dataset_dir = args.dataset_dir.resolve()
    errors: list[str] = []

    try:
        manifest = read_json(dataset_dir / "dataset-manifest.json")
        files = manifest.get("files", {}) if isinstance(manifest, dict) else {}
        evidence_rows = read_jsonl(dataset_dir / files.get("evidence", "evidence.jsonl"))
        case_rows = read_jsonl(dataset_dir / files.get("cases", "cases.jsonl"))
        oracle_rows = read_jsonl(dataset_dir / files.get("design_oracles", "design-oracles.jsonl"))
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    validators = {name: load_validator(path) for name, path in SCHEMA_PATHS.items()}
    errors.extend(schema_errors("dataset-manifest.json", [(None, manifest)], validators["manifest"]))
    errors.extend(schema_errors("evidence.jsonl", evidence_rows, validators["evidence"]))
    errors.extend(schema_errors("cases.jsonl", case_rows, validators["cases"]))
    errors.extend(schema_errors("design-oracles.jsonl", oracle_rows, validators["oracles"]))

    evidence = [record for _, record in evidence_rows]
    cases = [record for _, record in case_rows]
    oracles = [record for _, record in oracle_rows]
    if not errors:
        errors.extend(semantic_errors(manifest, evidence, cases, oracles))

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        print(f"validation failed: {len(errors)} error(s)", file=sys.stderr)
        return 1

    print_summary(manifest, evidence, cases, oracles)
    print("evaluation dataset validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
