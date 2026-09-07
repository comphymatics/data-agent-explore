"""DRAFT dataset integrity and quality, distinct from benchmark answer scoring."""
from collections import Counter
from .contracts import assert_draft, fingerprint
from .sampler import dimensions
from .raw_verifier import validate_case_sources
from evaluation.cases.schema import PILOT_TARGETS
from evaluation.benchmark.result_contract import CATEGORIES


def describe(cases,entities,relations,aliases,inventory):
    count=len(cases); categories=Counter(c["category"] for c in cases)
    spans=Counter(c["source_span"] for c in cases); levels=Counter(c["difficulty_suggested"] for c in cases)
    documents={row["path"] for row in inventory}; covered={doc for c in cases for doc in c["source_documents"]}&documents
    normalized_queries=[" ".join(c["query"].casefold().split()) for c in cases]
    motifs=Counter(c["motif_signature"] for c in cases)
    supported=sum(c["parser_supported"] for c in cases); blind=sum(c["parser_blind_spot"] for c in cases)
    cross=spans["cross_document"]/count if count else 0
    warnings=[f"{cat}: {categories[cat]}/{target} recommended candidates" for cat,target in PILOT_TARGETS.items() if categories[cat]<target]
    if cross<.6: warnings.append("cross-document candidate fraction below recommended 60%; necessity still requires review")
    unverified=[{"case_id":c["case_id"],"candidate_id":e["id"]} for c in cases
                for e in [*c["gold_candidate"],*c["support_relation_candidates"]] if not e["raw_verified"]]
    return {"total_candidates":count,"candidate_entities":len(entities),"candidate_relations":len(relations),
            "category_distribution":{cat:categories[cat] for cat in CATEGORIES},"source_span_distribution":dict(spans),
            "cross_document_ratio":cross,"difficulty_distribution":dict(levels),
            "entity_distribution":dict(Counter(e["type"] for e in entities)),
            "document_coverage":{"covered":sorted(covered),"uncovered":sorted(documents-covered),
                                 "ratio":len(covered)/len(documents) if documents else None},
            "parser_supported_cases":supported,"parser_blind_spot_cases":blind,
            "parser_supported_ratio":supported/count if count else None,"parser_blind_spot_ratio":blind/count if count else None,
            "alias_collisions":aliases["collisions"],"unverified_gold_candidates":unverified,
            "unconfirmed_negative_candidates":[c["case_id"] for c in cases if c["candidate_kind"]=="negative_candidate"],
            "duplicate_query_rate":(count-len(set(normalized_queries)))/count if count else 0,
            "similar_query_rate":sum(max(0,n-1) for n in motifs.values())/count if count else 0,
            "similarity_definition":"same category, hop count and entity-type motif; diagnostic, not semantic equivalence",
            "diversity_coverage":sorted([list(d) for d in {v for c in cases for v in dimensions(c)}]),
            "quota_warnings":warnings,"approval":"DRAFT only; raw_verified is not semantic or human approval"}


def validate_dataset(cases,entities,relations,aliases,inventory):
    artifacts=[cases,entities,relations,aliases]
    assert_draft(artifacts)
    ids=[e["id"] for e in entities]; edge_ids=[e["id"] for e in relations]; case_ids=[c["case_id"] for c in cases]
    if any(len(values)!=len(set(values)) for values in (ids,edge_ids,case_ids)): raise ValueError("duplicate candidate IDs")
    known=set(ids); edge_map={r["id"]:r for r in relations}; entity_map={e["id"]:e for e in entities}
    for record in [*entities,*relations]:
        if record.get("review_status")!="DRAFT" or record.get("candidate_origin") not in {"parser","raw_independent","both"}:
            raise ValueError("candidate provenance/status missing")
        for field in ("source_documents","source_locations","generation_method","parser_supported","raw_verified"):
            if field not in record: raise ValueError("candidate provenance missing: "+field)
        if not all(isinstance(record[k],bool) for k in ("parser_supported","raw_verified")):
            raise ValueError("verification/support markers must be booleans")
    for edge in relations:
        if edge["source"] not in known or edge["target"] not in known: raise ValueError("dangling candidate relation")
    for entry in aliases["entities"]:
        if entry["canonical_id"] not in known: raise ValueError("alias refers to unknown entity")
        if entry.get("review_status")!="DRAFT" or entry.get("type")!=entity_map[entry["canonical_id"]]["type"]:
            raise ValueError("Alias requires DRAFT status and the candidate entity type")
    for case in cases:
        if case.get("review_status")!="DRAFT" or case["category"] not in CATEGORIES: raise ValueError("invalid DRAFT Case")
        if not isinstance(case.get("query"),str) or not case["query"].strip(): raise ValueError("missing candidate query")
        if case.get("requires_human_confirmation") is not True: raise ValueError("human confirmation cannot be disabled")
        for entity in case["gold_candidate"]:
            if entity.get("id") not in known or entity!=entity_map[entity["id"]]: raise ValueError("Case entity candidate provenance drift")
        for relation in case["support_relation_candidates"]:
            if relation.get("id") not in edge_map or relation!=edge_map[relation["id"]]: raise ValueError("Case relation candidate provenance drift")
        if case["candidate_kind"]=="negative_candidate":
            if case["gold_candidate"] or not case["expected_empty"] or case.get("generation_method")!=["human_supplied_negative_review_scope"]:
                raise ValueError("negative candidate must remain unconfirmed and cannot derive absence from Parser JSON")
        elif not case["gold_candidate"] or case.get("candidate_construction_hash")!=fingerprint([case["gold_candidate"],case["support_relation_candidates"]]):
            raise ValueError("candidate construction changed outside deterministic generation")
    checks=[validate_case_sources(c,[row["path"] for row in inventory]) for c in cases]
    return {"valid":True,"source_valid":all(c["valid"] for c in checks),"draft_only":True,"case_count":len(cases),"source_checks":checks,
            "requires_source_review":sum(not c["valid"] for c in checks)}
