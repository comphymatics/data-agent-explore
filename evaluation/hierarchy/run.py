"""Independent, fixture-only ablation. Gold is supplied only to this consumer.

Run: uv run --isolated --extra dev python -m evaluation.hierarchy.run --out /tmp/hierarchy-ablation
"""
import argparse
from copy import deepcopy
from dataclasses import asdict
import json
from pathlib import Path
from statistics import mean

from enterprise_data_context.compiler import ContextCompiler
from enterprise_data_context.runtime import from_compiled
from explore_agent import ExploreAgent
from explore_agent.telemetry import estimate
from .sample import sample_fragments, sample_config


def sample_cases():
    # Expectations never enter source fragments, build policy, routing or retrieval.
    return [
        {"id": "A", "query": "RSRP有哪些现有模型可以提供？", "category": "exact_anchor", "mode": "direct",
         "relevant": ["RSRP", "LTE MR Logical Model", "LTE_PERIODIC_MR", "LTE_MR_NEW"]},
        {"id": "B", "query": "地铁弱覆盖需要哪些数据？", "category": "broad_cross_document", "mode": "hierarchical", "view": "analysis",
         "branches": ["地铁覆盖分析", "弱覆盖诊断"], "relevant": ["地铁覆盖分析", "弱覆盖诊断", "RSRP", "位置", "小区", "LTE MR Logical Model", "LTE_PERIODIC_MR"]},
        {"id": "C", "query": "有哪些数据可以描述小区无线覆盖质量？", "category": "purpose_to_data", "mode": "hierarchical", "view": "analysis",
         "branches": ["弱覆盖诊断"], "relevant": ["地铁覆盖分析", "弱覆盖诊断", "RSRP", "位置", "小区", "LTE MR Logical Model", "LTE_PERIODIC_MR"]},
        {"id": "D", "query": "LTE_PERIODIC_MR属于哪个主题域和主题？", "category": "model_to_analysis", "mode": "direct",
         "relevant": ["LTE_PERIODIC_MR", "LTE MR Logical Model", "小区"]},
        {"id": "E", "query": "一个没有Topic标签的新模型应该归到哪里？", "category": "unknown", "mode": "hierarchical", "view": "domain", "relevant": []},
        {"id": "F", "query": "RSRP用于弱覆盖时还需要哪些数据？", "category": "cross_domain", "mode": "hybrid", "view": "analysis",
         "branches": ["弱覆盖诊断", "地铁覆盖分析"], "relevant": ["地铁覆盖分析", "弱覆盖诊断", "RSRP", "位置", "小区", "LTE MR Logical Model", "LTE_PERIODIC_MR", "LTE_MR_NEW"]},
        {"id": "G", "query": "无线覆盖主题有哪些数据？", "category": "inferred_organization", "mode": "hierarchical", "view": "domain",
         "branches": ["无线覆盖"], "relevant": ["LTE MR Logical Model", "LTE_PERIODIC_MR", "LTE_MR_NEW", "小区"]},
    ]


def ratio(n, d):
    return n / d if d else None


def average(rows, key):
    vs = [r[key] for r in rows if r.get(key) is not None]
    return mean(vs) if vs else None


def evaluate_variant(compiled, cases, *, top_k=6, token_budget=5000):
    """Reusable read-only scorer; only user-visible queries/options cross into Explore."""
    agent = ExploreAgent(from_compiled(compiled).retrieval)
    index = compiled["hierarchy"]
    names = {c.name: c.path for c in compiled["contexts"]}
    rows = []
    for case in cases:
        bundle = agent.explore(case["query"], top_k=top_k, token_budget=token_budget)
        relevant = {names.get(n, n) for n in case["relevant"]}
        retrieved = set(bundle.selected_context_ids)
        tp = len(relevant & retrieved)
        precision = ratio(tp, len(retrieved))
        recall = ratio(tp, len(relevant))
        f1 = 2 * precision * recall / (precision + recall) if precision is not None and recall is not None and precision + recall else 0. if relevant else None
        trace = bundle.retrieval_trace
        expected_branches = {p for p, n in index.nodes.items() if n["name"] in case.get("branches", [])}
        branches = set(trace["selected_branches"])
        members = set()
        for p in branches:
            members.update(index.aggregate_pages[p]["views"][trace["hierarchy_view"]]["L2"]["members"])
        rows.append({"case_id": case["id"], "category": case["category"], "query": case["query"],
            "precision": precision, "recall": recall, "f1": f1,
            "query_llm_tokens": bundle.telemetry["model_tokens_reported"] if bundle.telemetry["model_token_usage_complete"] else None,
            "delivered_context_tokens_estimated": estimate(asdict(bundle)), "tool_calls": bundle.telemetry["tool_calls"],
            "routing_accuracy": float(trace["mode"] == case["mode"]),
            "hierarchy_entry_accuracy": float(trace["hierarchy_view"] == case["view"]) if case.get("view") else None,
            "branch_recall_at_k": ratio(len(branches & expected_branches), len(expected_branches)),
            "aggregate_context_precision": ratio(len(members & relevant), len(members)),
            "selected_context_ids": sorted(retrieved), "selected_branches": sorted(branches), "mode": trace["mode"],
            "missing_context": bundle.missing_context, "truncated": bundle.truncated,
            "unknown_topic_remains_unclassified": not any(e["active"] and index.nodes[e["parent_id"]]["kind"] == "topic"
                for e in index.parents.get(names["UNKNOWN_MODEL"], [])) if "UNKNOWN_MODEL" in names else None})
    metric_names = ("precision", "recall", "f1", "query_llm_tokens", "delivered_context_tokens_estimated", "tool_calls",
                    "routing_accuracy", "hierarchy_entry_accuracy", "branch_recall_at_k", "aggregate_context_precision")
    models = [c for c in compiled["contexts"] if c.context_type in {"logical-model", "physical-model"}]
    uncovered = [c for c in models if not c.sections.get("topic")]
    inferred = {e["child_id"] for e in index.edges if e["provenance"].get("source_relation") == "semantic_overlay"}
    candidates = [e for e in index.edges if e["status"] == "CANDIDATE"]
    # This sample's only approved placement expectation is independent of production inputs.
    expected_placements = {(names.get("LTE_MR_NEW"), "无线覆盖")}
    diagnostics = {"hierarchy_candidate_precision": ratio(sum((e["child_id"], index.nodes[e["parent_id"]]["name"]) in expected_placements for e in candidates), len(candidates)),
                   "inference_coverage": ratio(sum(c.path in inferred for c in uncovered), len(uncovered)),
                   "unclassified_rate": ratio(sum(index.classification(c.path)["status"] == "unclassified" for c in models), len(models)),
                   "topic_unclassified_rate": ratio(sum(not any(e["active"] and index.nodes[e["parent_id"]]["kind"] == "topic" for e in index.parents[c.path]) for c in models), len(models)),
                   "candidate_count": len(candidates)}
    return {"summary": {k: average(rows, k) for k in metric_names}, "diagnostics": diagnostics,
            "categories": {category: {k: average([r for r in rows if r["category"] == category], k) for k in metric_names} for category in sorted({r["category"] for r in rows})},
            "cases": rows}


def run_sample():
    source = sample_fragments()
    variants = {}
    for name, overrides in (("Data Explore", {}), ("Hierarchy disabled", {"hierarchy_enabled": False}),
                            ("Semantic inference disabled", {"inference_enabled": False})):
        config = {**sample_config(), **overrides}
        compiled = ContextCompiler(hierarchy_config=config).compile_fragments(deepcopy(source))
        variants[name] = evaluate_variant(compiled, sample_cases())
    return {"schema": "hierarchy-ablation/v1", "evidence_scope": "SYNTHETIC_ONLY", "headline_benchmark": False,
            "query_llm": "disabled; zero actual query LLM calls", "context_token_measurement": "unicode-aware estimate of delivered ContextBundle",
            "candidate_precision_note": "null when no candidate placements; no live LLM inference evaluated",
            "variants": variants}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="/tmp/hierarchy-ablation")
    args = parser.parse_args()
    output = Path(args.out); output.mkdir(parents=True, exist_ok=True)
    report = run_sample()
    (output / "sample-ablation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    lines = ["# Semantic Hierarchy synthetic ablation", "", "Synthetic only; independent of the four-system E2E leaderboard. Query LLM disabled. Context tokens are estimates.", "",
             "| Variant | Recall | Precision | F1 | Query LLM tokens | Delivered context tokens | Tool calls | Routing accuracy |",
             "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for name, value in report["variants"].items():
        s = value["summary"]
        lines.append("| " + name + " | " + " | ".join(f"{s[k]:.3f}" if s[k] is not None else "n/a" for k in ("recall", "precision", "f1", "query_llm_tokens", "delivered_context_tokens_estimated", "tool_calls", "routing_accuracy")) + " |")
    lines += ["", "No real-data effectiveness claim follows from this small sample. Full diagnostics, per-category results, unknowns and missing coverage are retained in the JSON report."]
    (output / "sample-ablation.md").write_text("\n".join(lines) + "\n")
    print(json.dumps({"output": str(output), "variants": {k: v["summary"] for k, v in report["variants"].items()}}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
