"""Bounded relational motifs produce unapproved candidate answer sets, never Gold."""
from copy import deepcopy
from .contracts import fingerprint, provenance, RELATION_TYPES
from .entity_graph import union
from .query_generator import generate_query


def difficulty(records,hops,span):
    types={r.get("type") for r in records if r.get("type")}
    ambiguity=any(r.get("conflicts") or r.get("alias_collision") for r in records)
    if ambiguity or span=="unknown" or (span=="cross_document" and len(types)>=3):
        return "hard","ambiguity/missing source or cross-document combination of at least three entity types"
    if span=="cross_document" or hops>=2 or any(len(r.get("name_variants",[]))>1 for r in records):
        return "medium","cross-document, multi-hop or explicit-ID name variants"
    return "easy","single-document exact anchor, one-hop motif"


def generate_candidates(graph,profile,paraphraser=None):
    cases=[]; seen=set(); duplicate_count=0

    def emit(category,anchor,edges,hops=1,direction=""):
        nonlocal duplicate_count
        if not edges: return
        ids=sorted({anchor,*[endpoint for edge in edges for endpoint in (edge["source"],edge["target"])]})
        entities=[graph.entities[cid] for cid in ids]
        # All support stays attached to the candidate, including builder-only field ownership.
        records=[*entities,*edges]
        documents=sorted({doc for row in records for doc in row["source_documents"]})
        locations=[]
        for row in records: locations=union(locations,row["source_locations"])
        signature=fingerprint([category,ids,sorted(e["id"] for e in edges)])
        if signature in seen: duplicate_count+=1; return
        seen.add(signature)
        span="cross_document" if len(documents)>1 else "single_document" if documents else "unknown"
        level,reason=difficulty(records,hops,span)
        parser_supported=all(row["parser_supported"] for row in records)
        has_raw=any(row["candidate_origin"] in {"raw_independent","both"} for row in records)
        origin="both" if has_raw and any(row["parser_supported"] for row in records) else "parser" if parser_supported else "raw_independent"
        facets={"technology":[],"topic":[],"business_object":[],"metric":[],"logical_model":[],"physical_model":[]}
        typemap={"business_objects":"business_object","metrics":"metric","logical_models":"logical_model","physical_models":"physical_model"}
        for entity in entities:
            if entity["type"] in typemap: facets[typemap[entity["type"]]].append(entity["id"])
            for key in facets:
                value=entity.get("facets",{}).get(key)
                if value: facets[key]=union(facets[key],value if isinstance(value,list) else [value])
        contributions={doc:[row["id"] for row in records if doc in row["source_documents"]] for doc in documents}
        case={"case_id":"draft-"+signature[:20],"category":category,"candidate_kind":"positive_candidate",
              "anchor_entity":anchor,"gold_candidate":deepcopy(entities),
              "relation_candidates":deepcopy([e for e in edges if e["relation"] in RELATION_TYPES]),
              "support_relation_candidates":deepcopy(edges),"expected_empty":False,
              "requires_human_confirmation":True,"difficulty_suggested":level,"difficulty":level,
              "difficulty_reason":reason,"source_span":span,"tags":["generated_draft"],"facets":facets,
              "motif_signature":category+":"+str(hops)+":"+",".join(sorted({e["type"] for e in entities})),
              "hops":hops,"source_contributions":contributions,
              "cross_document_rationale":("候选答案涉及多份资料："+"；".join(doc+" 提供 "+", ".join(ids) for doc,ids in contributions.items())+
                  "。需人工确认各文档不可替代，排除重复资料造成的伪跨文档。") if span=="cross_document" else None,
              **provenance(origin,documents,locations,"deterministic_relation_motif",all(r["raw_verified"] for r in records))}
        case["parser_supported"]=parser_supported
        case["parser_blind_spot"]=any(r["candidate_origin"]=="raw_independent" for r in records)
        case["candidate_construction_hash"]=fingerprint([case["gold_candidate"],case["support_relation_candidates"]])
        case["query"],case["query_generation"]=generate_query(category,graph.entities[anchor]["name"],profile,direction,paraphraser)
        cases.append(case)

    models={"physical_models","logical_models"}
    for entity in sorted(graph.entities.values(),key=lambda e:e["id"]):
        cid=entity["id"]; typ=entity["type"]
        if typ=="metrics":
            emit("metric_to_model",cid,graph.outgoing(cid,{"supported_by"}))
        if typ=="purposes":
            edges=graph.outgoing(cid,{"requires_metric","requires_dimension"})
            model_edges=[e for first in edges for e in graph.outgoing(first["target"],{"supported_by"})]
            field_edges=[e for model in model_edges for e in graph.outgoing(model["target"],{"has_field"})]
            emit("purpose_to_data",cid,edges+model_edges+field_edges,3 if field_edges else 2 if model_edges else 1)
        if typ in models:
            metric_edges=[e for e in graph.relations.values() if e["relation"]=="supported_by" and e["target"]==cid]
            purpose_edges=[e for e in graph.relations.values() if e["relation"]=="requires_metric" and any(m["source"]==e["target"] for m in metric_edges)]
            if purpose_edges: emit("model_to_analysis",cid,metric_edges+purpose_edges,2)
            emit("model_to_business",cid,graph.outgoing(cid,{"belongs_to_object"}))
            emit("field_discovery",cid,graph.outgoing(cid,{"has_field"}))
            for relation,label in (("upstream","上游"),("downstream","下游")):
                emit("lineage_impact",cid,graph.outgoing(cid,{relation}),direction=label)

    for seed in profile.negative_candidates:
        query=seed.get("query")
        if not isinstance(query,str) or not query.strip(): raise ValueError("negative seed requires a human-supplied query")
        documents=seed.get("source_documents",[])
        if not documents or not set(documents)<=graph.documents: raise ValueError("negative seed requires known review-scope raw documents")
        span="cross_document" if len(set(documents))>1 else "single_document"
        signature=fingerprint(["negative",query,sorted(documents)])
        if signature in seen: duplicate_count+=1; continue
        seen.add(signature)
        cases.append({"case_id":"draft-"+signature[:20],"category":"negative","candidate_kind":"negative_candidate",
            "query":query,"query_generation":{"method":"human_supplied_negative_seed"},
            "gold_candidate":[],"relation_candidates":[],"support_relation_candidates":[],
            "expected_empty":True,"requires_human_confirmation":True,"difficulty":"hard","difficulty_suggested":"hard",
            "difficulty_reason":"missing information must be independently reviewed", "source_span":span,
            "cross_document_rationale":"需联合审核声明范围内的全部资料；多文档缺失结论尚未确认。" if span=="cross_document" else None,
            "empty_rationale_candidate":seed.get("review_instruction","必须人工确认当前材料不足；禁止以 Parser JSON 缺项作为不存在的证据。"),
            "tags":["generated_draft","negative_candidate"],"facets":{},"motif_signature":"negative:review_scope",
            "parser_blind_spot":False,
            **provenance("raw_independent",documents,[],"human_supplied_negative_review_scope",False)})
    return cases,{"duplicate_motifs_removed":duplicate_count}
