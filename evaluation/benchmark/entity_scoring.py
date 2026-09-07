from .result_contract import ENTITY_TYPES


def score(normalized, gold, optional=None, forbidden=None, valid=True):
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
    return {"recall":recall,"precision":precision,"f1":f1,"matched":sorted(correct),
        "returned":sorted(actual),"unknown":sorted(normalized.unknown),"forbidden":sorted(actual&forbidden),
        "per_type":{typ:{"matched":len(normalized.entities[typ]&set(gold.get(typ,[]))) if valid else 0,
                          "required":len(set(gold.get(typ,[])))} for typ in ENTITY_TYPES},
        "gold_count":len(required),"returned_count":count,"accepted_count":len(acceptable)}
