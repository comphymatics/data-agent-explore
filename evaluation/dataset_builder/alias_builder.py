"""Candidate aliases only. Homonyms are reported, not merged."""
from collections import defaultdict
from evaluation.normalization.entity_registry import normalized


def build_aliases(entities):
    entries=[]; aliases=defaultdict(set)
    for entity in sorted(entities,key=lambda e:e["id"]):
        names=list(dict.fromkeys([entity["name"],*entity["name_variants"],*entity["aliases"]]))
        entries.append({"canonical_id":entity["id"],"type":entity["type"],"aliases":names,
                        "source_documents":entity["source_documents"],"generation_method":"candidate names/profile aliases",
                        "review_status":"DRAFT"})
        for name in names: aliases[normalized(name)].add(entity["id"])
    collisions=[{"code":"alias_collision","alias":name,"entity_ids":sorted(ids),"action":"human disambiguation; never auto-merge"}
                for name,ids in sorted(aliases.items()) if len(ids)>1]
    return {"entities":entries,"collisions":collisions}
