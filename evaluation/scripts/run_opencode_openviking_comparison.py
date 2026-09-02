#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evaluation.benchmark.runner import run_benchmark


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare OpenCode Explore with OpenViking retrieval.")
    parser.add_argument("--dataset-dir", required=True, type=Path)
    parser.add_argument("--corpus-dir", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument(
        "--systems",
        nargs="+",
        default=["opencode_explore", "openviking"],
        choices=["opencode_explore", "openviking"],
    )
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--include-variants", action="store_true")
    parser.add_argument("--case-id", action="append", dest="case_ids")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--skip-unavailable", action="store_true")
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()
    try:
        summary = run_benchmark(
            dataset_dir=args.dataset_dir,
            corpus_dir=args.corpus_dir,
            config_path=args.config,
            output_dir=args.output_dir,
            systems=args.systems,
            repeats=args.repeats,
            include_variants=args.include_variants,
            case_ids=set(args.case_ids) if args.case_ids else None,
            resume=args.resume,
            skip_unavailable=args.skip_unavailable,
            preflight_only=args.preflight_only,
        )
    except (OSError, ValueError, RuntimeError, KeyError) as exc:
        print(f"comparison failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
