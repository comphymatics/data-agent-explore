#!/usr/bin/env python3
"""Run governed LLM inference and optionally publish a candidate-only snapshot."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path

from jsonschema import Draft202012Validator

from enterprise_data_context.compiler import ContextCompiler
from enterprise_data_context.inference import (
    SemanticInferencePipeline,
    load_llm_inference_config,
    provider_from_config,
)
from enterprise_data_context.persistence import load_compiled, save_compiled


ROOT = Path(__file__).parents[1]


def write_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build governed CANDIDATE semantic relations with an LLM"
    )
    parser.add_argument("--snapshot", required=True, help="Base immutable Context snapshot")
    parser.add_argument("--config", required=True, help="LLM inference JSON config")
    parser.add_argument("--out", required=True, help="Inference report output directory")
    parser.add_argument(
        "--source-path", action="append", default=None,
        help="Limit inference to one scenario/analysis path; repeatable",
    )
    parser.add_argument(
        "--enriched-out",
        help="Optionally publish a new snapshot containing candidate relations",
    )
    args = parser.parse_args()

    config = load_llm_inference_config(args.config)
    if not config.enabled:
        raise SystemExit("LLM inference config is disabled; set enabled=true after review")
    compiled = load_compiled(args.snapshot)
    provider = provider_from_config(config)
    run = SemanticInferencePipeline(config, provider).run(compiled, args.source_path)

    schema = json.loads(
        (ROOT / "contracts" / "semantic-inference-run.schema.json").read_text(encoding="utf-8")
    )
    Draft202012Validator.check_schema(schema)
    errors = list(Draft202012Validator(schema).iter_errors(run.report))
    if errors:
        raise ValueError(f"inference report failed schema validation: {errors[0].message}")

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    write_json(out / "inference-report.json", run.report)
    fragment_text = "\n".join(
        json.dumps(asdict(fragment), ensure_ascii=False) for fragment in run.fragments
    )
    (out / "candidate-fragments.jsonl").write_text(
        fragment_text + ("\n" if fragment_text else ""), encoding="utf-8"
    )

    enriched_manifest = None
    if args.enriched_out:
        inference_fingerprint = sha256(
            json.dumps(run.report, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        sources = [
            {"id": source_id, "fingerprint": fingerprint}
            for source_id, fingerprint in compiled.get("source_fingerprints", {}).items()
        ]
        sources.append({
            "id": f"llm-inference:{run.report['run_id']}",
            "fingerprint": inference_fingerprint,
        })
        enriched = ContextCompiler().compile_fragments(
            [*compiled["fragments"], *run.fragments],
            documents=compiled.get("documents", []),
            sources=sources,
        )
        enriched["inference_runs"] = [*compiled.get("inference_runs", []), run.report]
        enriched["coverage_declaration"] = dict(compiled.get("coverage_declaration", {}))
        enriched_manifest = save_compiled(enriched, args.enriched_out)

    print(json.dumps({
        "run_id": run.report["run_id"],
        "status": run.report["status"],
        "source_count": run.report["source_count"],
        "proposal_count": run.report["proposal_count"],
        "rejection_count": run.report["rejection_count"],
        "error_count": run.report["error_count"],
        "report": str(out / "inference-report.json"),
        "candidate_fragments": str(out / "candidate-fragments.jsonl"),
        "enriched_manifest": enriched_manifest,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
