from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

from evaluation.benchmark.io import read_jsonl
from evaluation.construction import generate_case_candidates, generate_evidence_candidates


ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "source-materials" / "templates"
EXAMPLES = ROOT / "evaluation" / "examples"
CONSTRUCTION = ROOT / "evaluation" / "construction"
CONTRACTS = ROOT / "evaluation" / "contracts"


def validator(name: str) -> Draft202012Validator:
    schema = json.loads((CONTRACTS / name).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def test_template_json_generates_schema_valid_draft_evidence(tmp_path):
    output = tmp_path / "evidence"
    report = generate_evidence_candidates(TEMPLATES, output)
    records = read_jsonl(output / "evidence-candidates.jsonl")
    assert report["evidence_candidate_count"] == len(records)
    assert len(records) > 100
    assert all(record["review_status"] == "DRAFT" for record in records)
    assert all(record["source"]["source_version"].startswith("sha256:") for record in records)
    evidence_validator = validator("evidence-record.schema.json")
    errors = [error for record in records for error in evidence_validator.iter_errors(record)]
    assert not errors


def test_approved_evidence_generates_draft_cases_blueprints_and_deficits(tmp_path):
    output = tmp_path / "cases"
    report = generate_case_candidates(
        EXAMPLES / "evidence.jsonl",
        CONSTRUCTION / "pilot-quotas.json",
        output,
    )
    cases = read_jsonl(output / "candidate-cases.jsonl")
    blueprints = read_jsonl(output / "case-blueprints.jsonl")
    assert report["selected_candidates"] == len(cases) == len(blueprints)
    assert report["eligible_gold_evidence"] == 7
    assert report["quota_deficits"]["insufficient_context"] == 3
    assert all(case["review_status"] == "DRAFT" for case in cases)
    assert any(case["subtype"] == "multi_layer" for case in cases)
    assert any(case["scenario_family"] == "model_design_preparation" for case in cases)

    case_validator = validator("evaluation-case.schema.json")
    blueprint_validator = validator("case-blueprint.schema.json")
    assert not [error for case in cases for error in case_validator.iter_errors(case)]
    assert not [error for blueprint in blueprints for error in blueprint_validator.iter_errors(blueprint)]
    assert all(
        blueprint["oracle_required"]
        == (blueprint["candidate_case"]["scenario_family"] == "model_design_preparation")
        for blueprint in blueprints
    )
