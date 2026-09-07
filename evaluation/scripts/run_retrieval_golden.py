"""Run serving ablations and all required quality/cost gates on synthetic fixtures."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
from enterprise_data_context.runtime import from_compiled
from explore_agent import ExploreAgent
from explore_agent.evaluation import evaluate, assert_golden_gate
from evaluation.retrieval_golden.fixtures import corpus, cases, FixtureEnvironment, FixtureSemanticProvider


def run(semantic_config=None):
    reports = {}
    for name, mode, provider in (("lexical_ablation", "baseline", None), ("hybrid", "hybrid", None),
                                  ("bounded_fixture", "hybrid", FixtureSemanticProvider())):
        compiled = corpus()
        compiled["page_index"].mode = mode
        agent = ExploreAgent(from_compiled(compiled).retrieval, environment_adapter=FixtureEnvironment(), semantic_provider=provider)
        reports[name] = evaluate(agent, cases())
    if semantic_config:
        from enterprise_data_context.inference.config import load_llm_inference_config
        from explore_agent.bounded import HTTPStructuredProvider
        config=load_llm_inference_config(semantic_config)
        if not config.enabled:
            raise ValueError("semantic config is disabled")
        config.api_key()  # validate availability without printing credentials
        provider=HTTPStructuredProvider(config.base_url,config.model,config.api_key_env)
        agent=ExploreAgent(from_compiled(corpus()).retrieval,environment_adapter=FixtureEnvironment(),semantic_provider=provider)
        reports["live_semantic"]=evaluate(agent,cases(),progress=lambda row: print(
            "live",row["case_id"],"passed="+str(row["passed"]),
            "semantic="+",".join(x["status"] for x in row["telemetry"]["semantic_calls"]),flush=True))
    return reports


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="evaluation/retrieval_golden/report.json")
    parser.add_argument("--gate", action="store_true")
    parser.add_argument("--semantic-config", help="Optional enabled local LLM config; only synthetic fixture data is sent")
    args = parser.parse_args()
    reports = run(args.semantic_config)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"validation_scope": "synthetic fixtures; lexical ablation shares v2 runtime; MetaOne is a fixture; live LLM only in live_semantic",
        "reports": {name: asdict(report) for name, report in reports.items()}}, ensure_ascii=False, indent=2)+"\n")
    for name, report in reports.items():
        print(name, json.dumps({k:v for k,v in asdict(report).items() if k != "cases"}, ensure_ascii=False))
    if args.gate:
        for name in (["hybrid", "bounded_fixture", "live_semantic"] if args.semantic_config else ["hybrid", "bounded_fixture"]):
            assert_golden_gate(reports[name], minimums={"anchor_recall":1, "bundle_recall":1, "bundle_precision":1,
                "binding_precision":1, "focused_expansion_success":1}, maximums={"tool_calls":3, "token_cost":10000},
                baseline=reports["hybrid"] if name!="hybrid" else None,
                max_regressions={"anchor_recall":0,"bundle_recall":0,"bundle_precision":0,"coverage_accuracy":0,"binding_precision":0,"focused_expansion_success":0,"tool_calls":0,"token_cost":5000})


if __name__ == "__main__":
    main()
