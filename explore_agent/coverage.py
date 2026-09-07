"""Coverage is a requirement/entity claim with evidence, never a bundle OR."""
from collections import defaultdict
from hashlib import sha256
from dataclasses import dataclass, asdict

STATES = {"SATISFIED", "PARTIAL", "MISSING", "UNKNOWN", "NOT_APPLICABLE"}
RESOLVED = {"SATISFIED", "NOT_APPLICABLE"}
ASPECTS = {"business_meaning", "purpose", "business_object", "metrics", "dimensions",
           "models", "fields", "grain", "lineage", "formula", "constraints", "attributes", "counters", "join_keys"}
ENV_ASPECTS = {"models", "metrics", "dimensions", "fields", "grain", "lineage"}
RELATION_ASPECTS = {
    "models": {"supported_by", "uses_model", "implements_logical_model"},
    "metrics": {"uses_metric", "provides_metric"},
    "dimensions": {"uses_dimension", "has_dimension"},
    "business_object": {"maps_to_business_object", "maps_to_attribute"},
    "purpose": {"has_purpose", "analyzes"},
}
ENV_TYPES = {"models": {"physical-model", "logical-model", "aggregate-model"},
             "metrics": {"metric", "measure"}, "dimensions": {"dimension"}, "fields": {"field"}}


@dataclass(frozen=True)
class CoverageRequirement:
    id: str
    entity: str
    aspect: str
    layer: str = "REFERENCE"
    entity_name: str = ""
    selector: str | None = None

    def to_dict(self):
        return {k: v for k, v in asdict(self).items() if v is not None}


def conclusion(req, status, proofs, reason, context_refs=None):
    """UNKNOWN cites the inspected/requested context, never fabricated source evidence."""
    return {**req, "status": status, "evidence": proofs, "reason": reason,
            "context_refs": list(dict.fromkeys(context_refs or [req["entity"]]))}


def requirement(entity, aspect, layer="REFERENCE", name=None, selector=None):
    rid = layer.lower()+":"+sha256(str(entity).encode()).hexdigest()[:12]+":"+aspect
    row = {"id": rid, "entity": entity, "entity_name": name or entity, "aspect": aspect, "layer": layer}
    if selector:
        row.update(id=rid+":"+sha256(selector.encode()).hexdigest()[:8], selector=selector)
    return row


def validate_requirements(rows):
    if not isinstance(rows, list) or not rows or len(rows) > 64:
        raise ValueError("requirements must contain 1 to 64 entries")
    rows = [row.to_dict() if isinstance(row, CoverageRequirement) else row for row in rows]
    ids = set()
    for row in rows:
        if (not isinstance(row, dict) or set(row)-{"id", "entity", "entity_name", "aspect", "layer", "selector"} or
            not all(isinstance(row.get(k), str) and row[k] for k in ("id", "entity", "aspect", "layer")) or
            row["aspect"] not in ASPECTS or row["layer"] not in {"REFERENCE", "ENVIRONMENT"} or row["id"] in ids):
            raise ValueError("invalid or duplicate coverage requirement")
        if "selector" in row and (not isinstance(row["selector"], str) or not row["selector"].strip()):
            raise ValueError("selector must be a non-empty string")
        ids.add(row["id"])
    return [dict(row, entity_name=row.get("entity_name") or row["entity"]) for row in rows]


def infer_requirements(query, hits, anchor_ids, aspects, environment_required):
    named = [h for h in hits if h["name"].casefold() in query.casefold()]
    anchors = named or [h for h in hits if h["path"] in anchor_ids][:1]
    entities = [(h["path"], h["name"]) for h in anchors] or [("$query", query)]
    rows = []
    for entity, name in entities:
        for aspect in aspects:
            rows.append(requirement(entity, aspect, name=name))
            if environment_required and aspect in ENV_ASPECTS:
                rows.append(requirement(entity, aspect, "ENVIRONMENT", name))
    return rows


def assess(requirements, hits, expansions, environment):
    by_path = {hit["path"]: hit for hit in hits}
    result = {}
    for req in requirements:
        if req["layer"] == "ENVIRONMENT":
            result[req["id"]] = assess_environment(req, environment)
            continue
        entity = req["entity"]
        paths = ([entity] if entity in by_path else [] if "://" in entity else
                 [h["path"] for h in hits if h["name"].casefold() == req["entity_name"].casefold()])
        proofs = []
        for path in paths:
            support = by_path[path].get("support", []) + expansions.get(path, {}).get("support", [])
            proofs += [s for s in support if s["aspect"] == req["aspect"]]
            related = expansions.get(path, {}).get("related", {})
            for relation in related.get("outgoing", []):
                if relation["relation"] not in RELATION_ASPECTS.get(req["aspect"], set()) or not relation.get("evidence"):
                    continue
                target = relation["context"]["path"]
                if target not in by_path:
                    continue
                for proof in by_path[target].get("support", []):
                    if proof["aspect"] == req["aspect"]:
                        proofs.append({**proof, "via": path, "relation_evidence": relation["evidence"]})
            # A fixed, evidence-bearing composition supports purpose -> metric -> model.
            # Both pages arrived in the same bounded batch; no extra traversal tools.
            if req["aspect"]=="models":
                for first in related.get("outgoing",[]):
                    if first["relation"]!="uses_metric" or not first.get("evidence"):
                        continue
                    middle=first["context"]["path"]
                    if middle not in by_path:
                        continue
                    for second in expansions.get(middle,{}).get("related",{}).get("outgoing",[]):
                        if second["relation"] not in {"supported_by","uses_model"} or not second.get("evidence"):
                            continue
                        target=second["context"]["path"]
                        for proof in by_path.get(target,{}).get("support",[]):
                            if proof["aspect"]=="models":
                                proofs.append({**proof,"via":[path,middle],"relation_evidence":first["evidence"]+second["evidence"],"composition_rule":"uses_metric_supported_by/v1"})
            if req["aspect"] == "lineage":
                lineage = expansions.get(path, {}).get("lineage", {})
                for relation in lineage.get("outgoing", []) + lineage.get("incoming", []):
                    if relation.get("evidence"):
                        proofs.append({"path": path, "section": "lineage", "aspect": "lineage",
                                       "status": "EXPLICIT", "evidence": relation["evidence"], "conflicted": False})
        if req.get("selector"):
            selector=req["selector"].casefold()
            elements=[element for path in paths for element in expansions.get(path,{}).get("elements",[])
                      if selector==element["element_id"].casefold() or selector in [s.casefold() for s in element.get("identifiers",[])]]
            declarations=[p for p in proofs if p.get("coverage_status") and p.get("selector")==req["selector"]]
            proofs=[{**p,"truncated":False,"element_ids":[e["element_id"] for e in elements if e["path"]==p["path"] and e["section"]==p["section"]]}
                    for p in proofs if not p.get("coverage_status") and any(e.get("evidence") and e["path"]==p["path"] and e["section"]==p["section"] for e in elements)] + declarations
        proofs = [p for p in proofs if p.get("evidence") and p.get("status") in {"EXPLICIT", "DERIVED"}]
        proofs = [p for p in proofs if not p.get("coverage_status") or
                  (p.get("status")=="EXPLICIT" and p.get("authoritative") and p.get("declaration_reason") and
                   p.get("selector")==req.get("selector") and
                   (p["coverage_status"]!="MISSING" or p.get("complete")))]
        if proofs:
            states={p.get("coverage_status","SATISFIED") for p in proofs}
            status = "PARTIAL" if len(paths)>1 or len(states)>1 or any(p.get("conflicted") or p.get("truncated") for p in proofs) else next(iter(states))
            reason = "conflicting_or_incomplete_evidence" if status == "PARTIAL" else "entity_scoped_evidence"
        else:
            status = "UNKNOWN"
            reason = "no_evidence_in_partial_corpus"
        result[req["id"]] = conclusion(req,status,proofs,reason,[*paths,*[p["path"] for p in proofs if p.get("path")]])
    return result


def assess_environment(req, environment):
    from .binding import snapshot_evidence
    # Provider may declare an exact scoped assessment. MISSING needs complete inventory proof.
    declarations = []
    for row in environment.requirement_coverage:
        entity_keys={req["entity"]} if ":" in req["entity"] else {req["entity"],req["entity_name"]}
        if (row.get("entity") in entity_keys and row.get("aspect") == req["aspect"] and row.get("selector")==req.get("selector") and
            row.get("status") in STATES and row.get("evidence")):
            if row["status"] == "MISSING" and not (row.get("complete") is True and row.get("authoritative") is True):
                continue
            if row["status"]=="NOT_APPLICABLE" and not (row.get("authoritative") is True and row.get("reason")):
                continue
            if row.get("assertion_status","EXPLICIT")!="EXPLICIT":
                continue
            if environment.capabilities and not snapshot_evidence(environment,row["evidence"]):
                continue
            declarations.append(row)
    if declarations:
        statuses={r["status"] for r in declarations}
        return conclusion(req,next(iter(statuses)) if len(statuses)==1 else "PARTIAL",
                          [e for r in declarations for e in r["evidence"]],"provider_scoped_assessment")
    def matches_entity(asset):
        if ":" in req["entity"]:
            return req["entity"] in {asset.get("id"),asset.get("attributes",{}).get("reference_path")}
        return req["entity_name"].casefold() in {str(asset.get(k, "")).casefold() for k in ("id","name","code")}
    matches = [asset for asset in environment.assets if matches_entity(asset) and
               asset.get("assertion_status") == "EXPLICIT" and asset.get("evidence") and
               (not environment.capabilities or snapshot_evidence(environment,asset["evidence"]))]
    if len(matches)>1:
        return conclusion(req,"PARTIAL",[{"asset_id":a["id"],"evidence":a["evidence"]} for a in matches],"ambiguous_environment_identity",[a["id"] for a in matches])
    proofs = []
    for asset in matches:
        if not req.get("selector") and (asset.get("type") in ENV_TYPES.get(req["aspect"], set()) or asset.get("attributes", {}).get(req["aspect"])):
            proofs.append({"asset_id": asset["id"], "evidence": asset["evidence"]})
        if req["aspect"] == "lineage":
            proofs += [r for r in environment.relations if r.get("source_id") == asset["id"] and
                       r.get("predicate") in {"UPSTREAM_OF", "DOWNSTREAM_OF", "USES", "DERIVED_FROM"} and
                       r.get("assertion_status")=="EXPLICIT" and not req.get("selector") and r.get("evidence") and
                       (not environment.capabilities or snapshot_evidence(environment,r["evidence"]))]
    return conclusion(req,"SATISFIED" if proofs else "UNKNOWN",proofs,
                      "authoritative_entity_evidence" if proofs else "environment_"+environment.state.value.lower(),
                      [a["id"] for a in matches])


def summarize_coverage(coverage, layer="REFERENCE"):
    groups = defaultdict(list)
    for row in coverage.values():
        if row["layer"] == layer:
            groups[row["aspect"]].append(row["status"])
    return {aspect: all(s in RESOLVED for s in states) for aspect, states in groups.items()}


def missing_requirements(coverage):
    missing = []
    for rid, row in coverage.items():
        if row["status"] not in RESOLVED:
            missing.extend([rid, row["aspect"] if row["layer"] == "REFERENCE" else "environment_coverage:"+row["aspect"]])
    return list(dict.fromkeys(missing))
