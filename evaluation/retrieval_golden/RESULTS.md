# Retrieval regression results — 2026-09-07

The implementation passed **85 Python tests**, JSON Schema validation and Python
compilation. The synthetic Golden suite and a real DeepSeek-V4-Flash run both
passed the quality/cost gates. MetaOne was a fixture in all Golden runs.

| Metric | Lexical candidate ablation | Hybrid | Hybrid + live bounded semantics |
|---|---:|---:|---:|
| Passed cases | 9/10 | 10/10 | 10/10 |
| Anchor Recall | 90.0% | 100% | 100% |
| Bundle Recall | 84.6% | 100% | 100% |
| Bundle Precision | 100% | 100% | 100% |
| Coverage Accuracy | 100% | 100% | 100% |
| Identity Binding Precision | 100% | 100% | 100% |
| Focused Expansion Success | 100% | 100% | 100% |
| Mean Context + Environment Tool Calls | 2.5 | 2.6 | 2.6 |
| Mean token cost estimate | 1,116.9 | 1,264.8 | 2,682.5 |

The lexical comparison shares the new runtime; it is not an evaluation of the
historical runtime. Hybrid uses the versioned local concept/subword encoder, not a
trained dense embedding model. This is a small regression suite, not a claim of
production retrieval quality: it contains 10 anchor labels, 13 required bundle
labels, 9 coverage checks, 1 positive identity binding and 1 focused element label.
Negative identity/availability/candidate cases additionally gate each case.

In the real-model run, **17 of 20 calls were accepted**, two unsupported intent
upgrades were rejected, and one reasoner timed out. All three used deterministic
fallback. The provider reported **13,112 model tokens** for 19 calls; token usage
for the timed-out call is unknown. The cost metric combines tool/environment
payload estimates with reported model usage, reserving the output cap when model
usage is missing. It is not a monetary cost or a fully measured token total.

The initial real-model run failed two cost gates because bare metric queries
triggered additional environment lookups. The router now requires query evidence
for intent upgrades; the thresholds were preserved. The corrected run passed
without increasing tool calls relative to hybrid.

Artifacts:

- [Deterministic/fixture report](report.json)
- [Real-model report and per-call telemetry](report-live.json)
- [Initial rejected real-model run](report-live-initial.json)
- [Commands, oracle format and validation scope](README.md)

The new requirement Coverage schema, Page-scoped Element search, binding
separation, timeout/grounding guards, and snapshot/replay checks are covered by
regression tests. Live MetaOne payload calibration and a trained embedding encoder
still need separate environment-specific evaluations.
