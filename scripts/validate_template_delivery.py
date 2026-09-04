"""Validate a real parser Template JSON delivery without publishing a snapshot."""

import argparse
import json
from pathlib import Path

from enterprise_data_context.delivery import validate_template_delivery


parser = argparse.ArgumentParser(description="Validate a parser Template JSON batch")
parser.add_argument("--input", required=True, help="Delivered Template JSON file or directory")
parser.add_argument("--report", help="Optional path for the machine-readable validation report")
args = parser.parse_args()

batch = validate_template_delivery(args.input)
report = batch["delivery_report"]
if args.report:
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
print(json.dumps(report, ensure_ascii=False, indent=2))
