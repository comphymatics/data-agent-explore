"""Deterministic diversity-first sampling, with explicit caps and exclusion reasons."""
from collections import Counter
from evaluation.cases.schema import PILOT_TARGETS

DIMENSIONS=("category","technology","topic","business_object","metric","logical_model","physical_model",
            "source_document","source_span","difficulty")


def dimensions(case):
    result={key:case.get("facets",{}).get(key,[]) for key in DIMENSIONS}
    result.update(category=[case["category"]],source_document=case["source_documents"],
                  source_span=[case["source_span"]],difficulty=[case["difficulty_suggested"]])
    return {(key,str(value)) for key,values in result.items() for value in values}


def sample(cases,profile):
    remaining=sorted(cases,key=lambda c:c["case_id"]); selected=[]; excluded=[]; seen_queries=set()
    counts={key:Counter() for key in ("entity","document","topic","motif","category")}; covered=set()
    while remaining and len(selected)<profile.target_count:
        eligible=[]
        for case in remaining:
            entities=[e["id"] for e in case["gold_candidate"]]
            constraints=[("entity",entities,profile.max_cases_per_entity),
                         ("document",case["source_documents"],profile.max_cases_per_document),
                         ("topic",case.get("facets",{}).get("topic",[]),profile.max_cases_per_topic),
                         ("motif",[case["motif_signature"]],profile.max_cases_per_motif)]
            reason=next((kind+"_cap" for kind,values,limit in constraints if any(counts[kind][str(v)]>=limit for v in values)),None)
            query=" ".join(case["query"].casefold().split())
            if query in seen_queries: reason="duplicate_query"
            if reason: excluded.append({"case_id":case["case_id"],"reason":reason}); continue
            novelty=len(dimensions(case)-covered)
            unmet=max(0,1-counts["category"][case["category"]]/PILOT_TARGETS[case["category"]])
            eligible.append((novelty+5*unmet,case,constraints))
        if not eligible: break
        eligible.sort(key=lambda item:(-item[0],item[1]["case_id"]))
        _,chosen,constraints=eligible[0]
        selected.append(chosen); covered.update(dimensions(chosen))
        seen_queries.add(" ".join(chosen["query"].casefold().split()))
        for kind,values,_ in constraints:
            counts[kind].update({str(v):1 for v in values})
        counts["category"][chosen["category"]]+=1
        rejected={r["case_id"] for r in excluded}
        remaining=[c for c in remaining if c["case_id"]!=chosen["case_id"] and c["case_id"] not in rejected]
    excluded.extend({"case_id":c["case_id"],"reason":"target_count_reached"} for c in remaining if c["case_id"] not in {r["case_id"] for r in excluded})
    return selected,{"dimensions":list(DIMENSIONS),"covered_values":len(covered),"excluded":excluded,
                     "similarity_policy":"category/hop/entity-type motif cap plus exact normalized query dedup"}
