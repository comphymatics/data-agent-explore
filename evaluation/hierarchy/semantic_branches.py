"""Real local embedding on synthetic branches; no credentials or source uploads.

uv run --isolated --extra dev --extra dense python -m evaluation.hierarchy.semantic_branches --out /tmp/trained-branches.json
"""
import argparse
import json
from pathlib import Path
from enterprise_data_context.indexes.dense import FastEmbedEncoder, DEFAULT_MODEL
from enterprise_data_context.indexes.aggregate import AggregatePageIndex
from .semantic_fixture import build_semantic_fixture, SEMANTIC_CASES


def run():
    compiled = build_semantic_fixture()
    index = compiled["hierarchy"]
    index.aggregate_index = AggregatePageIndex(FastEmbedEncoder(DEFAULT_MODEL, local_files_only=True))
    index.aggregate_index.sync(index.aggregate_pages)
    rows = []
    for query, expected in SEMANTIC_CASES:
        for method in ("lexical", "hybrid"):
            hits = index.aggregate_index.search(query, ["analysis"], top_k=3, method=method)
            rows.append({"query": query, "expected": expected, "method": method, "hits": hits,
                "warnings": index.aggregate_index.last_warnings,
                "hit_at_1": bool(hits and index.aggregate_pages[hits[0]["path"]]["name"] == expected),
                "hit_at_3": any(index.aggregate_pages[h["path"]]["name"] == expected for h in hits)})
    return {"evidence_scope": "TRAINED_LOCAL_ENCODER_SYNTHETIC_CORPUS", "encoder": index.aggregate_index.encoder.version,
        "trained_encoder_available": not any(r["warnings"] for r in rows),
        "summary": {method: {key: sum(r[key] for r in rows if r["method"] == method) / len(SEMANTIC_CASES)
                             for key in ("hit_at_1", "hit_at_3")} for method in ("lexical", "hybrid")}, "cases": rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    result = run()
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "cases"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
