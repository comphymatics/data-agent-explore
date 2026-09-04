"""Audit a compiled Context snapshot against explicit pilot acceptance thresholds."""

import argparse
import json
from pathlib import Path

from jsonschema import Draft202012Validator

from enterprise_data_context.audit import audit_compiled_snapshot
from enterprise_data_context.persistence import load_compiled


ROOT = Path(__file__).parents[1]
parser = argparse.ArgumentParser(description="Audit an immutable Enterprise Data Context snapshot")
parser.add_argument("--snapshot", required=True, help="Snapshot root or immutable version directory")
parser.add_argument("--out", help="Optional output path for the audit report")
parser.add_argument("--require-delivery-manifest", action="store_true")
parser.add_argument("--require-complete-coverage", action="store_true")
parser.add_argument("--min-cross-source-confirmed", type=int, default=0)
parser.add_argument("--max-unresolved-ratio", type=float, default=1.0)
parser.add_argument("--max-orphan-ratio", type=float, default=1.0)
args = parser.parse_args()

compiled = load_compiled(args.snapshot)
report = audit_compiled_snapshot(
    compiled,
    require_delivery_manifest=args.require_delivery_manifest,
    require_complete_coverage=args.require_complete_coverage,
    min_cross_source_confirmed=args.min_cross_source_confirmed,
    max_unresolved_ratio=args.max_unresolved_ratio,
    max_orphan_ratio=args.max_orphan_ratio,
)
schema = json.loads(
    (ROOT / "contracts" / "context-snapshot-audit.schema.json").read_text(encoding="utf-8")
)
Draft202012Validator(schema).validate(report)
if args.out:
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps(report, ensure_ascii=False, indent=2))
raise SystemExit(0 if report["status"] == "PASSED" else 1)
