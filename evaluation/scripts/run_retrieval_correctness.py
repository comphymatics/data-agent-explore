"""Freeze Router/Reasoner; compare lexical and trained dense retrieval only."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
from enterprise_data_context.indexes.dense import FastEmbedEncoder
from enterprise_data_context.runtime import from_compiled
from explore_agent import ExploreAgent
from explore_agent.evaluation import evaluate, assert_golden_gate
from evaluation.retrieval_golden.correctness import corpus, cases, CorrectnessEnvironment


def run(encoder=None):
    reports={}
    for mode in ("baseline","hybrid"):
        compiled=corpus()
        compiled["page_index"].mode=mode
        if encoder is not None:
            compiled["page_index"].encoder=encoder
        agent=ExploreAgent(from_compiled(compiled).retrieval,environment_adapter=CorrectnessEnvironment())
        reports[mode]=evaluate(agent,cases())
    return reports


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--dense-model",required=True)
    parser.add_argument("--output",default="evaluation/retrieval_golden/correctness-report.json")
    parser.add_argument("--gate",action="store_true")
    args=parser.parse_args()
    encoder=FastEmbedEncoder(args.dense_model)
    reports=run(encoder)
    payload={"scope":"synthetic corpus; local trained dense; fixture MetaOne; Router/Reasoner unchanged and semantic providers disabled",
             "encoder":encoder.version,"reports":{k:asdict(v) for k,v in reports.items()}}
    Path(args.output).write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n")
    for name,report in reports.items():
        print(name,json.dumps({k:v for k,v in asdict(report).items() if k!="cases"},ensure_ascii=False))
        for case in report.cases:
            if not case["passed"]:
                print("FAILED",case["case_id"],case["metrics"],case["coverage_checks"])
    if args.gate:
        assert_golden_gate(reports["hybrid"],minimums={"anchor_recall":1,"bundle_recall":1,"bundle_precision":1,
            "binding_precision":1,"focused_expansion_success":1},maximums={"tool_calls":3,"token_cost":14000})


if __name__=="__main__":
    main()
