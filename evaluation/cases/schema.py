from evaluation.benchmark.result_contract import CATEGORIES, ENTITY_TYPES


def validate_cases(rows,registry,documents,smoke=False):
    ids=set()
    for row in rows:
        if row.get("case_id") in ids or not row.get("case_id") or not row.get("query"):
            raise ValueError("cases require unique IDs and nonempty queries")
        ids.add(row["case_id"])
        if row.get("category") not in CATEGORIES:
            raise ValueError("category must be Q1 through Q6")
        if row.get("review_status") not in ({"APPROVED","FIXTURE"} if smoke else {"APPROVED"}):
            raise ValueError("formal cases require human-approved Gold")
        span=row.get("difficulty",{}).get("source_span")
        sources=set(row.get("source_documents",[]))
        if span not in {"single_document","cross_document"} or not sources<=documents or not sources:
            raise ValueError("invalid source-span declaration")
        if span=="single_document" and len(sources)!=1:
            raise ValueError("single-document cases require exactly one source")
        if span=="cross_document" and (len(sources)<2 or not row.get("cross_document_rationale")):
            raise ValueError("cross-document cases require multiple sources and a necessity rationale")
        gold=row.get("gold",{})
        if set(gold)-set(ENTITY_TYPES):
            raise ValueError("unsupported Gold entity type")
        required=set()
        for typ,values in gold.items():
            if not isinstance(values,list) or len(values)!=len(set(values)):
                raise ValueError("Gold values must be unique ID lists")
            for cid in values:
                if cid not in registry.entities or registry.entities[cid]["type"]!=typ:
                    raise ValueError("Gold ID missing or type mismatch")
            required.update(values)
        optional=set(row.get("optional",[])); forbidden=set(row.get("forbidden",[]))
        if not required:
            raise ValueError("entity recall cases require at least one required Gold entity")
        if not (optional|forbidden) <= set(registry.entities):
            raise ValueError("optional/forbidden IDs must belong to the scorer registry")
        if required&optional or (required|optional)&forbidden:
            raise ValueError("required/optional/forbidden sets must be disjoint")
    if not rows: raise ValueError("empty case set")
    return rows
