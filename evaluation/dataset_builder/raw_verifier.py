"""Raw location checks are explicit about their narrow scope; they never approve Gold."""
from evaluation.normalization.entity_registry import normalized
from .entity_graph import union
from collections import defaultdict


def locator_matches(location,unit):
    # Unsupported locator precision (e.g. cell/page not supplied by this Reader)
    # must not silently degrade into a document-level match.
    return all(value==unit["location"].get(key) for key,value in location.items() if key!="plane")


def verify_entities(graph,units):
    literals_index=defaultdict(set)
    for index,unit in enumerate(units):
        for literal in {normalized(unit["text"]),*[normalized(v) for v in unit["record"].values()]}:
            literals_index[literal].add(index)
    for candidate in graph.entities.values():
        locations=[loc for loc in candidate["source_locations"] if loc.get("plane")=="raw"]
        names={normalized(name) for name in [candidate["name"],*candidate["aliases"]]}
        matches=[]
        indexes={index for name in names for index in literals_index.get(name,[])}
        for index in sorted(indexes):
            unit=units[index]
            if unit["document"] not in candidate["source_documents"]: continue
            if locations and not any(locator_matches(loc,unit) for loc in locations): continue
            # Exact cell or full paragraph matches; substring matches are only navigation hints.
            matches.append(unit["location"])
        candidate["raw_verified"]=bool(matches)
        candidate["source_locations"]=union(candidate["source_locations"],[{"plane":"raw",**location} for location in matches])
        candidate["raw_verification"]={"state":"LOCATED" if matches else "UNVERIFIED",
            "scope":"literal name presence only; type/identity/meaning require human review","locations":matches}


def compare_raw_vs_parser(graph):
    return {"parser_only":[e["id"] for e in graph.entities.values() if e["candidate_origin"]=="parser"],
            "raw_independent_only":[e["id"] for e in graph.entities.values() if e["candidate_origin"]=="raw_independent"],
            "both":[e["id"] for e in graph.entities.values() if e["candidate_origin"]=="both"],
            "unverified":[e["id"] for e in graph.entities.values() if not e["raw_verified"]],
            "meaning":"raw_independent_only is a potential parser blind spot, not an automatically approved fact"}


def validate_case_sources(case,documents,units=None):
    documents=set(documents); errors=[]
    sources=set(case.get("source_documents",[]))
    if not sources: errors.append("no raw source documents")
    if not sources<=documents: errors.append("unknown source documents: "+", ".join(sorted(sources-documents)))
    expected="cross_document" if len(sources)>1 else "single_document" if sources else "unknown"
    if case.get("source_span")!=expected: errors.append("source_span mismatch")
    if expected=="cross_document" and not case.get("cross_document_rationale"): errors.append("cross-document rationale missing")
    for location in case.get("source_locations",[]):
        if location.get("plane")=="parser": continue
        if location.get("document") not in sources: errors.append("locator outside case sources")
        if units is not None and not any(locator_matches(location,unit) for unit in units): errors.append("raw locator not found")
    return {"case_id":case["case_id"],"valid":not errors,"errors":errors,
            "cross_document_necessity":"human review required; multiple sources may be duplicates"}
