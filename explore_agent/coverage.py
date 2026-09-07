"""Coverage is a requirement/entity claim with evidence, never a bundle OR."""
from collections import defaultdict
from hashlib import sha256

STATES = {"SATISFIED", "PARTIAL", "MISSING", "UNKNOWN"}
ASPECTS = {"business_meaning", "purpose", "business_object", "metrics", "dimensions",
           "models", "fields", "grain", "lineage", "formula", "constraints"}
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


def requirement(entity, aspect, layer="REFERENCE", name=None, selector=None):
    rid = layer.lower()+":"+sha256(str(entity).encode()).hexdigest()[:12]+":"+aspect
    row = {"id": rid, "entity": entity, "entity_name": name or entity, "aspect": aspect, "layer": layer}
    if selector:
        row.update(id=rid+":"+sha256(selector.encode()).hexdigest()[:8], selector=selector)
    return row


def validate_requirements(rows):
    if not isinstance(rows, list) or not rows or len(rows) > 64:
        raise ValueError("requirements must contain 1 to 64 entries")
    ids = set()
    for row in rows:
        if (not isinstance(row, dict) or set(row)-{"id", "entity", "entity_name", "aspect", "layer", "selector"} or
            not all(isinstance(row.get(k), str) and row[k] for k in ("id", "entity", "aspect", "layer")) or
            row["aspect"] not in ASPECTS or row["layer"] not in {"REFERENCE", "ENVIRONMENT"} or row["id"] in ids):
            raise ValueError("invalid or duplicate coverage requirement")
        if "selector" in row and (not isinstance(row["selector"], str) or not row["selector"].strip()):
            raise ValueError("selector must be a non-empty string")
        ids.add(row["id"])
    return [dict(row, entity_name=row.get("entity_name", row["entity"])) for row in rows]


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
        paths = [entity] if entity in by_path else [h["path"] for h in hits if h["name"].casefold() == req["entity_name"].casefold()]
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
            def leaves(value):
                if isinstance(value,dict):
                    return [s for v in value.values() for s in leaves(v)]
                if isinstance(value,list):
                    return [s for v in value for s in leaves(v)]
                return [str(value).casefold()]
            elements=[element for path in paths for element in expansions.get(path,{}).get("elements",[])
                      if selector==element["element_id"].casefold() or selector in leaves(element["value"])]
            proofs=[{**p,"truncated":False,"element_ids":[e["element_id"] for e in elements]}
                    for p in proofs if any(e.get("evidence") and e["path"]==p["path"] and e["section"]==p["section"] for e in elements)]
        proofs = [p for p in proofs if p.get("evidence") and p.get("status") in {"EXPLICIT", "DERIVED"}]
        if proofs:
            status = "PARTIAL" if any(p.get("conflicted") or p.get("truncated") for p in proofs) else "SATISFIED"
            reason = "conflicting_or_incomplete_evidence" if status == "PARTIAL" else "entity_scoped_evidence"
        else:
            status = "UNKNOWN"
            reason = "no_evidence_in_partial_corpus"
        result[req["id"]] = {**req, "status": status, "evidence": proofs, "reason": reason}
    return result


def assess_environment(req, environment):
    # Provider may declare an exact scoped assessment. MISSING needs complete inventory proof.
    for row in environment.requirement_coverage:
        if (row.get("entity") == req["entity_name"] and row.get("aspect") == req["aspect"] and row.get("selector")==req.get("selector") and
            row.get("status") in STATES and row.get("evidence")):
            if row["status"] == "MISSING" and not (row.get("complete") is True and row.get("authoritative") is True):
                continue
            return {**req, "status": row["status"], "evidence": row["evidence"], "reason": "provider_scoped_assessment"}
    matches = [asset for asset in environment.assets if req["entity_name"].casefold() in
               {str(asset.get(k, "")).casefold() for k in ("id", "name", "code")} and
               asset.get("assertion_status") == "EXPLICIT" and asset.get("evidence")]
    if len(matches)>1:
        return {**req,"status":"PARTIAL","evidence":[{"asset_id":a["id"],"evidence":a["evidence"]} for a in matches],"reason":"ambiguous_environment_identity"}
    proofs = []
    for asset in matches:
        if not req.get("selector") and (asset.get("type") in ENV_TYPES.get(req["aspect"], set()) or asset.get("attributes", {}).get(req["aspect"])):
            proofs.append({"asset_id": asset["id"], "evidence": asset["evidence"]})
        if req["aspect"] == "lineage":
            proofs += [r for r in environment.relations if r.get("source_id") == asset["id"] and
                       r.get("predicate") in {"UPSTREAM_OF", "DOWNSTREAM_OF", "USES", "DERIVED_FROM"} and r.get("evidence")]
    return {**req, "status": "SATISFIED" if proofs else "UNKNOWN", "evidence": proofs,
            "reason": "authoritative_entity_evidence" if proofs else "environment_"+environment.state.value.lower()}


def summarize_coverage(coverage, layer="REFERENCE"):
    groups = defaultdict(list)
    for row in coverage.values():
        if row["layer"] == layer:
            groups[row["aspect"]].append(row["status"])
    return {aspect: all(s == "SATISFIED" for s in states) for aspect, states in groups.items()}


def missing_requirements(coverage):
    missing = []
    for rid, row in coverage.items():
        if row["status"] != "SATISFIED":
            missing.extend([rid, row["aspect"] if row["layer"] == "REFERENCE" else "environment_coverage:"+row["aspect"]])
    return list(dict.fromkeys(missing))
