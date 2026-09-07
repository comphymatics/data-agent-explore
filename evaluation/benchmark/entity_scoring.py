from .result_contract import ENTITY_TYPES


def score(normalized, gold, optional=None, forbidden=None, valid=True, expected_empty=False, relations=None):
    required={c for values in gold.values() for c in values}
    allowed=required|set(optional or [])
    forbidden=set(forbidden or [])
    actual={c for values in normalized.entities.values() for c in values}
    correct=actual&required if valid else set()
    acceptable=(actual&allowed)-forbidden if valid else set()
    count=len(actual)+len(normalized.unknown)
    recall=len(correct)/len(required) if required else None
    precision=len(acceptable)/count if count and valid else (1.0 if not count and not required and valid else 0.0)
    f1=2*recall*precision/(recall+precision) if recall is not None and recall+precision else 0.0
    negative_correct=valid and count==0 and not normalized.relations and not normalized.unknown_relations
    relation_gold={tuple(e[k] for k in ("source","relation","target")) for e in (relations or [])}
    relation_correct=normalized.relations & relation_gold if valid else set()
    relation_count=len(normalized.relations)+len(normalized.unknown_relations)
    relation_recall=len(relation_correct)/len(relation_gold) if relation_gold else None
    relation_precision=len(relation_correct)/relation_count if relation_count else (0.0 if relation_gold else None)
    relation_f1=(2*relation_recall*relation_precision/(relation_recall+relation_precision)
                 if relation_recall and relation_precision else (0.0 if relation_gold else None))
    return {"recall":recall,"precision":precision if not expected_empty or count else None,
        "f1":f1 if not expected_empty else None,"matched":sorted(correct),
        "returned":sorted(actual),"unknown":sorted(normalized.unknown),"forbidden":sorted(actual&forbidden),
        "per_type":{typ:{"matched":len(normalized.entities[typ]&set(gold.get(typ,[]))) if valid else 0,
                          "required":len(set(gold.get(typ,[])))} for typ in ENTITY_TYPES},
        "gold_count":len(required),"returned_count":count,"accepted_count":len(acceptable),
        "expected_empty":expected_empty,
        "negative_correct":negative_correct if expected_empty else None,
        "negative_false_positive":bool(count or normalized.relations or normalized.unknown_relations) if expected_empty else None,
        "relation":{"annotated":relations is not None,"gold_count":len(relation_gold),
                    "returned_count":relation_count,"matched_count":len(relation_correct),
                    "recall":relation_recall if relations is not None else None,
                    "precision":relation_precision if relations is not None else None,
                    "f1":relation_f1 if relations is not None else None}}
