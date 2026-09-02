#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evaluation.construction import generate_case_candidates


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate deterministic DRAFT evaluation-case candidates from approved Evidence."
    )
    parser.add_argument("--evidence", required=True, type=Path)
    parser.add_argument(
        "--quotas",
        type=Path,
        default=ROOT / "evaluation" / "construction" / "pilot-quotas.json",
    )
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--max-paths", type=int, default=1000)
    args = parser.parse_args()
    try:
        report = generate_case_candidates(
            args.evidence.resolve(),
            args.quotas.resolve(),
            args.output_dir.resolve(),
            max_paths=args.max_paths,
        )
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"case candidate generation failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
