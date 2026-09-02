#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evaluation.construction import generate_evidence_candidates


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate DRAFT atomic Evidence candidates from parser Template JSON."
    )
    parser.add_argument("--templates", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument(
        "--authority",
        type=Path,
        help="Optional JSON object mapping evaluation source_type to authority rank",
    )
    args = parser.parse_args()
    try:
        authority = json.loads(args.authority.read_text(encoding="utf-8")) if args.authority else None
        if authority is not None and not isinstance(authority, dict):
            raise ValueError("authority file must contain a JSON object")
        report = generate_evidence_candidates(
            args.templates.resolve(),
            args.output_dir.resolve(),
            authority=authority,
        )
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"Evidence candidate generation failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
