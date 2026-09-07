"""Independent effect/cost metrics; no composite score or inferred missing cost."""
import csv
import json
from pathlib import Path
from statistics import mean, pstdev
from evaluation.benchmark.result_contract import ENTITY_TYPES


def stats(values):
    known=[v for v in values if v is not None]
    return {"mean":mean(known) if known else None,"std":pstdev(known) if known else None,
            "min":min(known) if known else None,"max":max(known) if known else None,
            "measured":len(known),"expected":len(values),"complete":len(known)==len(values)}


def micro(rows):
    required=sum(r["score"]["gold_count"] for r in rows)
    returned=sum(r["score"]["returned_count"] for r in rows)
    recall=sum(len(r["score"]["matched"]) for r in rows)/required if required else None
    precision=sum(r["score"]["accepted_count"] for r in rows)/returned if returned else (0.0 if required else None)
    f1=2*recall*precision/(recall+precision) if recall and precision else (0.0 if required else None)
    return {"recall":recall,"precision":precision,"f1":f1}


def diagnostic(rows):
    negative=[r["score"] for r in rows if r["score"].get("expected_empty")]
    relations=[r["score"]["relation"] for r in rows if r["score"].get("relation",{}).get("annotated")]
    required=sum(r["gold_count"] for r in relations)
    returned=sum(r["returned_count"] for r in relations)
    matched=sum(r["matched_count"] for r in relations)
    recall=matched/required if required else None
    precision=matched/returned if returned else (0.0 if required else None)
    f1=2*recall*precision/(recall+precision) if recall and precision else (0.0 if required else None)
    return {"negative_case_accuracy":sum(r["negative_correct"] for r in negative)/len(negative) if negative else None,
            "false_positive_rate":sum(r["negative_false_positive"] for r in negative)/len(negative) if negative else None,
            "negative_cases":len(negative),"relation_annotated_runs":len(relations),
            "relation_recall":recall,"relation_precision":precision,"relation_f1":f1}


def summary(rows):
    data={key:stats([r["score"][key] for r in rows]) for key in ("recall","precision","f1")}
    for key in ("query_llm_input_tokens","query_llm_output_tokens","query_llm_total_tokens",
                "delivered_context_tokens","tool_calls","retrieval_rounds","latency_ms"):
        data[key]=stats([r["result"].get(key) for r in rows])
    data["invalid_run_rate"]=sum(r["result"]["status"]!="OK" for r in rows)/len(rows) if rows else None
    data["runs"]=len(rows); data["micro"]=micro(rows); data.update(diagnostic(rows))
    repeats=sorted({r["repeat"] for r in rows})
    per_repeat=[{**micro([r for r in rows if r["repeat"]==repeat]),
                 **diagnostic([r for r in rows if r["repeat"]==repeat])} for repeat in repeats]
    data["repeat_statistics"]={k:stats([r[k] for r in per_repeat]) for k in (
        "recall","precision","f1","negative_case_accuracy","false_positive_rate","relation_recall","relation_precision","relation_f1")}
    data["per_type_recall"]={}
    for typ in ENTITY_TYPES:
        denom=sum(r["score"]["per_type"][typ]["required"] for r in rows)
        numer=sum(r["score"]["per_type"][typ]["matched"] for r in rows)
        data["per_type_recall"][typ]=numer/denom if denom else None
    return data


def write_csv(path,rows,columns):
    with open(path,"w",newline="",encoding="utf-8") as handle:
        writer=csv.DictWriter(handle,fieldnames=columns,extrasaction="ignore")
        writer.writeheader(); writer.writerows(rows)


def average(aggregate,key):
    value=aggregate[key]
    return value["mean"] if value["complete"] else None


def effect_cost(system,agg):
    return {"System":system,"Recall":agg["micro"]["recall"],"Precision":agg["micro"]["precision"],"F1":agg["micro"]["f1"],
            "AvgQueryLLMTokens":average(agg,"query_llm_total_tokens"),
            "AvgDeliveredContextTokens":average(agg,"delivered_context_tokens"),
            "AvgToolCalls":average(agg,"tool_calls"),"AvgLatency":average(agg,"latency_ms"),
            "InvalidRunRate":agg["invalid_run_rate"],"Runs":agg["runs"],
            "NegativeCaseAccuracy":agg["negative_case_accuracy"],"FalsePositiveRate":agg["false_positive_rate"],
            "RelationRecall":agg["relation_recall"],"RelationPrecision":agg["relation_precision"],"RelationF1":agg["relation_f1"]}


EFFECT_COLUMNS=["System","Recall","Precision","F1","AvgQueryLLMTokens","AvgDeliveredContextTokens",
                "AvgToolCalls","AvgLatency","InvalidRunRate","Runs","NegativeCaseAccuracy","FalsePositiveRate",
                "RelationRecall","RelationPrecision","RelationF1"]


def report(output,details,builds):
    output=Path(output); aggregates={}; leaderboard=[]; categories=[]; spans=[]; amortized=[]
    for system,build in builds.items():
        rows=[r for r in details if r["system"]==system]
        agg=summary(rows); aggregates[system]=agg
        agg["per_case"]={cid:summary([r for r in rows if r["case_id"]==cid]) for cid in sorted({r["case_id"] for r in rows})}
        avg=average(agg,"query_llm_total_tokens")
        leaderboard.append({**effect_cost(system,agg),
            "Status":build["status"] if agg["invalid_run_rate"]==0 or build["status"]!="OK" else "INCOMPLETE",
            "TotalQueryLLMTokens":sum(r["result"]["query_llm_total_tokens"] for r in rows) if avg is not None else None,
            "BuildLLMTokens":build["build_llm_total_tokens"],"BuildTimeMs":build["build_time_ms"],
            "RecallStd":agg["repeat_statistics"]["recall"]["std"],"F1Std":agg["repeat_statistics"]["f1"]["std"],
            "LLMUsageComplete":agg["query_llm_total_tokens"]["complete"] and build["build_llm_total_tokens"] is not None})
        for field,destination in (("category",categories),("source_span",spans)):
            for group in sorted({r[field] for r in rows}):
                sub=summary([r for r in rows if r[field]==group])
                destination.append({**effect_cost(system,sub),"Category" if field=="category" else "SourceSpan":group})
                if field=="source_span":
                    label="SingleDocument" if group=="single_document" else "CrossDocument"
                    leaderboard[-1][label+"Recall"]=sub["micro"]["recall"]
                    leaderboard[-1][label+"F1"]=sub["micro"]["f1"]
        for n in (1,10,100,1000):
            build_tokens=build["build_llm_total_tokens"]
            original=build["metadata"].get("original_build_llm_tokens",build_tokens)
            amortized.append({"System":system,"N":n,"AverageLLMTokensPerQuery":avg+build_tokens/n if avg is not None and build_tokens is not None else None,
                "ColdBuildEquivalentLLMTokensPerQuery":avg+original/n if avg is not None and original is not None else None,
                "ReusedSnapshot":build["metadata"].get("reused_snapshot")})
    write_csv(output/"leaderboard.csv",leaderboard,[*EFFECT_COLUMNS,"Status","TotalQueryLLMTokens","BuildLLMTokens","BuildTimeMs","RecallStd","F1Std","LLMUsageComplete","SingleDocumentRecall","SingleDocumentF1","CrossDocumentRecall","CrossDocumentF1"])
    write_csv(output/"category_breakdown.csv",categories,["System","Category",*EFFECT_COLUMNS[1:]])
    write_csv(output/"source_span_breakdown.csv",spans,["System","SourceSpan",*EFFECT_COLUMNS[1:]])
    write_csv(output/"amortized_cost.csv",amortized,["System","N","AverageLLMTokensPerQuery","ColdBuildEquivalentLLMTokensPerQuery","ReusedSnapshot"])
    write_csv(output/"effect_cost_scatter.csv",leaderboard,["System","Status","AvgQueryLLMTokens","Recall","F1","LLMUsageComplete"])
    (output/"statistics.json").write_text(json.dumps(aggregates,ensure_ascii=False,indent=2))
    return aggregates
