# Semantic Hierarchy synthetic ablation

Synthetic only; independent of the four-system E2E leaderboard. Query LLM disabled. Context tokens are estimates.

| Variant | Recall | Precision | F1 | Query LLM tokens | Delivered context tokens | Tool calls | Routing accuracy |
|---|---:|---:|---:|---:|---:|---:|---:|
| Data Explore | 1.000 | 0.550 | 0.734 | 0.000 | 16806.000 | 2.000 | 1.000 |
| Hierarchy disabled | 0.953 | 0.556 | 0.718 | 0.000 | 11942.556 | 2.000 | 0.222 |
| Lexical branch retrieval | 1.000 | 0.550 | 0.734 | 0.000 | 16362.444 | 2.000 | 1.000 |
| Hybrid branch retrieval | 1.000 | 0.550 | 0.734 | 0.000 | 16806.000 | 2.000 | 1.000 |
| Semantic inference disabled | 0.969 | 0.542 | 0.718 | 0.000 | 16683.222 | 2.000 | 1.000 |

No real-data effectiveness claim follows from this small sample. Full diagnostics, per-category results, unknowns and missing coverage are retained in the JSON report.
