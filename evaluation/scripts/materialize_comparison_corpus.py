#!/usr/bin/env python3
# LEGACY / NON-HEADLINE EVALUATION — official entry: python -m evaluation
from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evaluation.benchmark.corpus import materialize_corpus


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Materialize the same Gold-free Evidence corpus for OpenCode and OpenViking."
    )
    parser.add_argument("--dataset-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    try:
        manifest = materialize_corpus(args.dataset_dir, args.output_dir)
    except (OSError, ValueError, KeyError) as exc:
        print(f"corpus materialization failed: {exc}", file=sys.stderr)
        return 1
    print(
        f"materialized {manifest['record_count']} Evidence pages to "
        f"{args.output_dir.resolve()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
