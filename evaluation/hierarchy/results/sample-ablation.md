# Semantic Hierarchy synthetic ablation

Synthetic only; independent of the four-system E2E leaderboard. Query LLM disabled. Context tokens are estimates.

| Variant | Recall | Precision | F1 | Query LLM tokens | Delivered context tokens | Tool calls | Routing accuracy |
|---|---:|---:|---:|---:|---:|---:|---:|
| Data Explore | 0.875 | 0.624 | 0.791 | 0.000 | 14896.000 | 2.000 | 1.000 |
| Hierarchy disabled | 0.830 | 0.660 | 0.789 | 0.000 | 10157.429 | 2.000 | 0.286 |
| Semantic inference disabled | 0.875 | 0.624 | 0.791 | 0.000 | 14878.000 | 2.000 | 1.000 |

No real-data effectiveness claim follows from this small sample. Full diagnostics, per-category results, unknowns and missing coverage are retained in the JSON report.
