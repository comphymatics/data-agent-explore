from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "evaluation" / "scripts" / "validate_dataset.py"
EXAMPLES = ROOT / "evaluation" / "examples"


def run_validator(dataset_dir):
    return subprocess.run(
        [sys.executable, str(VALIDATOR), "--dataset-dir", str(dataset_dir)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_synthetic_evaluation_dataset_is_valid():
    result = run_validator(EXAMPLES)
    assert result.returncode == 0, result.stderr
    assert "evaluation dataset validation passed" in result.stdout


def test_validator_rejects_unknown_gold_evidence(tmp_path):
    for name in ("dataset-manifest.json", "evidence.jsonl", "cases.jsonl", "design-oracles.jsonl"):
        (tmp_path / name).write_text((EXAMPLES / name).read_text(encoding="utf-8"), encoding="utf-8")

    case_path = tmp_path / "cases.jsonl"
    cases = [json.loads(line) for line in case_path.read_text(encoding="utf-8").splitlines()]
    cases[0]["required_evidence"].append("ev-does-not-exist")
    case_path.write_text(
        "\n".join(json.dumps(case, ensure_ascii=False) for case in cases) + "\n",
        encoding="utf-8",
    )

    result = run_validator(tmp_path)
    assert result.returncode == 1
    assert "unknown Evidence IDs" in result.stderr
