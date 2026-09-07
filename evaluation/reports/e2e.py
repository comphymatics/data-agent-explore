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


def summary(rows):
    data={key:stats([r["score"][key] for r in rows]) for key in ("recall","precision","f1")}
    for key in ("query_tokens_input","query_tokens_output","query_tokens_total","tool_calls","retrieval_rounds","latency_ms"):
        data[key]=stats([r["result"][key] for r in rows])
    data["invalid_run_rate"]=sum(r["result"]["status"]!="OK" for r in rows)/len(rows) if rows else None
    data["runs"]=len(rows)
    data["micro"]=micro(rows)
    per_repeat=[micro([r for r in rows if r["repeat"]==repeat]) for repeat in sorted({r["repeat"] for r in rows})]
    data["repeat_statistics"]={k:stats([r[k] for r in per_repeat]) for k in ("recall","precision","f1")}
    data["per_type_recall"]={}
    for typ in ENTITY_TYPES:
        denom=sum(r["score"]["per_type"][typ]["required"] for r in rows)
        numer=sum(r["score"]["per_type"][typ]["matched"] for r in rows)
        data["per_type_recall"][typ]=numer/denom if denom else None
    return data


def micro(rows):
    required=sum(r["score"]["gold_count"] for r in rows)
    returned=sum(r["score"]["returned_count"] for r in rows)
    recall=sum(len(r["score"]["matched"]) for r in rows)/required if required else None
    precision=sum(r["score"]["accepted_count"] for r in rows)/returned if returned else (0.0 if required else None)
    f1=2*recall*precision/(recall+precision) if recall is not None and precision is not None and recall+precision else 0.0
    return {"recall":recall,"precision":precision,"f1":f1}


def write_csv(path,rows,columns):
    with open(path,"w",newline="",encoding="utf-8") as handle:
        writer=csv.DictWriter(handle,fieldnames=columns,extrasaction="ignore")
        writer.writeheader(); writer.writerows(rows)


def report(output,details,builds):
    output=Path(output); aggregates={}; leaderboard=[]; categories=[]; spans=[]; amortized=[]
    for system,build in builds.items():
        rows=[r for r in details if r["system"]==system]
        agg=summary(rows); aggregates[system]=agg
        agg["per_case"]={cid:summary([r for r in rows if r["case_id"]==cid]) for cid in sorted({r["case_id"] for r in rows})}
        query_cost=agg["query_tokens_total"]
        avg=query_cost["mean"] if query_cost["complete"] else None
        leaderboard.append({"System":system,"Status":build["status"] if agg["invalid_run_rate"]==0 or build["status"]!="OK" else "INCOMPLETE","Recall":agg["micro"]["recall"],
            "Precision":agg["micro"]["precision"],"F1":agg["micro"]["f1"],"AvgQueryTokens":avg,
            "TotalQueryTokens":sum(r["result"]["query_tokens_total"] for r in rows) if avg is not None else None,
            "BuildTokens":build["build_tokens_total"],"AvgToolCalls":agg["tool_calls"]["mean"] if agg["tool_calls"]["complete"] else None,
            "AvgLatency":agg["latency_ms"]["mean"],"InvalidRunRate":agg["invalid_run_rate"],"Runs":len(rows),
            "RecallStd":agg["repeat_statistics"]["recall"]["std"],"F1Std":agg["repeat_statistics"]["f1"]["std"],"TokenUsageComplete":query_cost["complete"] and build["build_tokens_total"] is not None})
        for span,label in (("single_document","SingleDocument"),("cross_document","CrossDocument")):
            selected=[r for r in rows if r["source_span"]==span]
            scoped=micro(selected)
            leaderboard[-1][label+"Recall"]=scoped["recall"] if selected else None
            leaderboard[-1][label+"F1"]=scoped["f1"] if selected else None
        for field,destination in [("category",categories),("source_span",spans)]:
            for group in sorted({r[field] for r in rows}):
                sub=summary([r for r in rows if r[field]==group])
                destination.append({"System":system,"Category":group,"Recall":sub["micro"]["recall"],
                    "Precision":sub["micro"]["precision"],"F1":sub["micro"]["f1"],
                    "Tokens":sub["query_tokens_total"]["mean"] if sub["query_tokens_total"]["complete"] else None,
                    "InvalidRunRate":sub["invalid_run_rate"],"Runs":sub["runs"]})
        for n in (1,10,100,1000):
            build_tokens=build["build_tokens_total"]
            original=build["metadata"].get("original_build_tokens",build_tokens)
            amortized.append({"System":system,"N":n,"AverageTokensPerQuery":avg+build_tokens/n if avg is not None and build_tokens is not None else None,
                "ColdBuildEquivalentTokensPerQuery":avg+original/n if avg is not None and original is not None else None,
                "ReusedSnapshot":build["metadata"].get("reused_snapshot")})
    write_csv(output/"leaderboard.csv",leaderboard,["System","Status","Recall","Precision","F1","AvgQueryTokens","TotalQueryTokens","BuildTokens","AvgToolCalls","AvgLatency","InvalidRunRate","Runs","RecallStd","F1Std","TokenUsageComplete","SingleDocumentRecall","SingleDocumentF1","CrossDocumentRecall","CrossDocumentF1"])
    for filename,rows in [("category_breakdown.csv",categories),("source_span_breakdown.csv",spans)]:
        write_csv(output/filename,rows,["System","Category","Recall","Precision","F1","Tokens","InvalidRunRate","Runs"])
    write_csv(output/"amortized_cost.csv",amortized,["System","N","AverageTokensPerQuery","ColdBuildEquivalentTokensPerQuery","ReusedSnapshot"])
    (output/"statistics.json").write_text(json.dumps(aggregates,ensure_ascii=False,indent=2))
    return aggregates
