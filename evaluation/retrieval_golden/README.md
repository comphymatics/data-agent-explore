# High-information retrieval regression

Run from the repository root:

```sh
uv run --isolated --extra dev pytest -q
uv run --isolated --extra dev python -m evaluation.scripts.run_retrieval_golden --gate
```

`fixtures.py` defines a small synthetic corpus and manually specified oracles.
It is independent of local `source-materials`, generated snapshots and network
services. It is test data, not an approved production Golden dataset or live
MetaOne evidence. The report names its validation scope explicitly.

The runner compares lexical candidate retrieval under the v2 runtime, hybrid
retrieval, and hybrid plus a structured semantic **fixture provider**. The latter
verifies bounded integration and grounding, not the quality of a real LLM. The
lexical ablation is not the pre-change historical system.

Reported metrics are micro-averaged Anchor Recall, Bundle Recall/Precision,
requirement-state Coverage Accuracy, Identity Binding Precision and Focused
Expansion Success. Cost metrics are mean Context + Environment Tool Calls and
serialized tool/normalized-environment token estimates plus reported model usage.
When model usage is unavailable, the cost estimate reserves the output cap instead
of counting the failed call as free. Raw hidden
provider-internal operations cannot be counted by a legacy adapter; telemetry
marks this incompleteness. Provider-reported model tokens remain separate.
Every report includes per-case results, token/call traces and metric denominators.
Unscored metrics are null; gates cannot accept an unscored required metric.

The cases cover exact and cross-language anchors, typed model relationships,
focused element selection, entity isolation, candidate exclusion, same-name false
bindings, authoritative scoped absence, unavailable environments, and conflicts.
Quality gates require no regression and cost ceilings. The bounded fixture permits
an explicit additional token allowance for its two model calls.

For a real Golden set, construct `EvaluationCase` records with canonical expected
paths, `expected_anchors`, a complete `relevant_contexts` precision oracle,
`expected_coverage` keys `LAYER|entity_name|aspect` (or append `|selector`, or use a requirement ID), expected identity pairs,
expected element IDs or exact leaf values, and `explore_options.requirements`.
Specify cost ceilings. Feed these to `evaluate` and `assert_golden_gate`; keep the
existing evaluation evidence approval workflow for production data. Do not infer
all relevant contexts from whatever the current retriever happened to return.

Coverage output changed from booleans to requirement assessments. Existing
`required_coverage` evaluation cases explicitly target the compatibility reference
projection; new cases should compare the four states directly. Existing
`EvaluationReport` positional fields remain usable.


An enabled local LLM configuration can additionally run the same cases through
`--semantic-config config/llm-inference.json --output evaluation/retrieval_golden/report-live.json --gate`.
Only synthetic evidence is transmitted. Inspect `semantic_calls.status` as well
as quality scores: a deterministic fallback may pass a retrieval case while the
model call times out or is rejected. `provider_tokens` is null when the endpoint
does not report usage or the call times out; this is unknown usage, not zero.
