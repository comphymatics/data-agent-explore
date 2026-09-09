# Semantic Hierarchy synthetic ablation

Synthetic only; independent of the four-system E2E leaderboard. Query LLM disabled. Context tokens are estimates.

| Variant | Recall | Precision | F1 | Query LLM tokens | Delivered context tokens | Tool calls | Routing accuracy |
|---|---:|---:|---:|---:|---:|---:|---:|
| Data Explore | 1.000 | 0.598 | 0.779 | 0.000 | 16051.000 | 2.000 | 1.000 |
| Hierarchy disabled | 0.873 | 0.602 | 0.735 | 0.000 | 10721.889 | 2.000 | 0.222 |
| Lexical branch retrieval | 1.000 | 0.598 | 0.779 | 0.000 | 16031.000 | 2.000 | 1.000 |
| Hybrid branch retrieval | 1.000 | 0.598 | 0.779 | 0.000 | 16051.000 | 2.000 | 1.000 |
| Semantic inference disabled | 0.906 | 0.574 | 0.736 | 0.000 | 15874.000 | 2.000 | 1.000 |

No real-data effectiveness claim follows from this small sample. Full diagnostics, per-category results, unknowns and missing coverage are retained in the JSON report.
