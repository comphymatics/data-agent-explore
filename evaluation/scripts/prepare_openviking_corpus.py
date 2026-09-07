#!/usr/bin/env python3
# LEGACY / NON-HEADLINE EVALUATION — official entry: python -m evaluation
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evaluation.benchmark.io import read_json
from evaluation.benchmark.openviking_import import import_corpus


def main() -> int:
    parser = argparse.ArgumentParser(description="Upload a materialized corpus to OpenViking.")
    parser.add_argument("--corpus-dir", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--no-wait", action="store_true")
    args = parser.parse_args()
    try:
        config = read_json(args.config).get("openviking", {})
        result = import_corpus(args.corpus_dir, config, wait=not args.no_wait)
    except (OSError, ValueError, RuntimeError, KeyError) as exc:
        print(f"OpenViking corpus import failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
