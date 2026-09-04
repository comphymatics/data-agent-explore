# Real-data pilot runbook

This runbook starts from the external parser's Template JSON delivery. It does not
read Word/Excel and does not treat missing source material as evidence of absence.

## 1. Validate the delivery boundary

```bash
uv run --isolated --extra dev python scripts/validate_template_delivery.py \
  --input <parser-delivery-directory> \
  --report <run-directory>/delivery-validation.json
```

For a governed pilot, the directory should include `delivery-manifest.json`. The
validation must report `PASSED`; file inventory, kind and SHA-256 checks must pass.

## 2. Build an immutable Reference Context snapshot

```bash
uv run --isolated --extra dev python scripts/build_template_inputs.py \
  --input <parser-delivery-directory> \
  --out <run-directory>/reference-context
```

The build must contain no quality errors. Warnings, unresolved references, conflicts
and partial coverage remain visible rather than being silently discarded.

## 3. Apply explicit pilot acceptance thresholds

Thresholds are selected for the declared pilot scope. Example:

```bash
uv run --isolated --extra dev python scripts/audit_context_snapshot.py \
  --snapshot <run-directory>/reference-context \
  --out <run-directory>/snapshot-audit.json \
  --require-delivery-manifest \
  --min-cross-source-confirmed 1 \
  --max-unresolved-ratio 0.80 \
  --max-orphan-ratio 0.80
```

Use `--require-complete-coverage` only when the parser owner has declared an
authoritative complete inventory for the exact scope. A failed threshold is a pilot
finding, not permission to hide missing context.

## 4. Generate bounded LLM candidates

```bash
uv run --isolated --extra dev python scripts/build_semantic_candidates.py \
  --snapshot <run-directory>/reference-context \
  --config config/llm-inference.json \
  --out <run-directory>/inference \
  --enriched-out <run-directory>/candidate-context
```

LLM output remains `CANDIDATE`. It cannot enter confirmed Backrefs, hierarchy or the
machine-facing Graph before a separate review/approval workflow exists.

## 5. Generate the review visualization

```bash
uv run --isolated --extra dev python scripts/generate_semantic_context_visualization.py \
  --snapshot <run-directory>/candidate-context \
  --output <run-directory>/semantic-context-browser.html
```

Record the delivery report, snapshot audit, association report, inference report,
`IndexVersion`, provider/model and prompt version together. Compare unresolved and
orphan ratios before and after deterministic mapping; assess LLM candidates by a
human-approved Golden Dataset rather than confidence alone.
