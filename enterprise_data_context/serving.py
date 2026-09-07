"""Machine-side intent policies and evidence-bearing Page projections."""
from dataclasses import asdict
from .indexes.page import CLASSIFICATION_FILTERS, FACET_ALIASES, facet_matches

RELATIONS = {
    "metric_to_models": {"supported_by", "uses_model", "uses_metric", "provides_metric", "implemented_by", "implements_logical_model"},
    "analysis_data_requirement": {"uses_metric", "uses_dimension", "uses_model", "supported_by", "has_purpose", "analyzes", "implements_logical_model"},
    "model_understanding": {"maps_to_business_object", "maps_to_attribute", "implements_logical_model", "has_dimension"},
    "impact_analysis": {"upstream", "downstream", "depends_on", "supported_by", "uses_model", "uses_metric", "implements_logical_model"},
}
LINEAGE = {"upstream", "downstream", "depends_on", "supported_by", "uses_model"}
ASPECT_SECTIONS = {
    "business_meaning": ("summary",), "purpose": ("analysis_purposes", "customer_value"),
    "business_object": ("primary_objects", "related_objects", "object_attributes"),
    "metrics": ("metrics", "metric_catalog"), "dimensions": ("dimensions",),
    "fields": ("important_fields", "attributes"), "grain": ("grain",),
    "formula": ("formula",), "constraints": ("constraints",), "models": (), "lineage": (),
}
TYPE_ASPECTS = {"metric": "metrics", "dimension": "dimensions", "analysis-purpose": "purpose",
                "physical-model": "models", "logical-model": "models", "business-object": "business_object"}


def allowed_page(page, types=None, scope=None):
    if page.identity_status not in {"EXPLICIT", "DERIVED"} or (types and page.context_type not in types):
        return False
    return not any(FACET_ALIASES.get(k, k) in CLASSIFICATION_FILTERS and
                   not facet_matches(page.facets.get(FACET_ALIASES.get(k, k)), v)
                   for k, v in (scope or {}).items()
                   if page.context_type in {"physical-model", "logical-model"})


def relation_allowed(relation, intent):
    return intent not in RELATIONS or relation in RELATIONS[intent]


def support_facts(page, context, level="L1", sections=None):
    visible = set(sections or page.l2)
    if level == "L0":
        visible &= {"summary", "identity"}
    # Field dictionaries are deliberately focused reads, not initial page documents.
    elif sections is None:
        visible -= {"important_fields", "attributes", "record_sources", "metric_catalog"}
    rows = []
    for aspect, keys in ASPECT_SECTIONS.items():
        for key in keys:
            if key not in visible or page.l2.get(key) in (None, "", [], {}):
                continue
            status = page.section_status.get(key, "EXPLICIT")
            evidence = [asdict(e) for e in context.evidence.get(key, [])]
            if status not in {"EXPLICIT", "DERIVED"} or not evidence:
                continue
            rows.append({"aspect": aspect, "section": key, "path": page.path,
                         "status": status, "evidence": evidence,
                         "conflicted": any(c.get("section") == key for c in page.conflicts)})
    aspect = TYPE_ASPECTS.get(page.context_type)
    identity_evidence = context.evidence.get("identity") or next(iter(context.evidence.values()), [])
    if aspect and identity_evidence:
        rows.append({"aspect": aspect, "section": "identity", "path": page.path,
                     "status": page.identity_status, "evidence": [asdict(e) for e in identity_evidence],
                     "conflicted": False})
    return rows


def rich_relations(service, path, kind, top_k, intent=None):
    """Project relations to rich page summaries; no graph-node traversal API."""
    result = {"outgoing": [], "incoming": []}
    for direction, side in (("out", "outgoing"), ("in", "incoming")):
        for edge in service.graph.neighbors(path, direction):
            if kind == "lineage" and edge["relation"] not in LINEAGE:
                continue
            if not relation_allowed(edge["relation"], intent):
                continue
            other = edge["target"] if direction == "out" else edge["source"]
            page = service.pages.get(other)
            if not page or not allowed_page(page):
                continue
            source = service.contexts.get(edge["source"])
            evidence = [asdict(e) for ref in source.references if ref.status == "CONFIRMED" and
                        ref.target_path == edge["target"] and ref.relation == edge["relation"] for e in ref.evidence] if source else []
            if source and not evidence:
                evidence = [asdict(e) for e in source.evidence.get("lineage."+edge["relation"], [])]
            result[side].append({"relation": edge["relation"], "context": {
                "path": other, "name": page.name, "type": page.context_type,
                "content": page.l0, "knowledge_layer": "REFERENCE"},
                "evidence": evidence, "status": "CONFIRMED"})
            if len(result[side]) >= top_k:
                break
    return result


class BundleAssembler:
    """Bounded machine completion followed by relevance/coverage/diversity selection."""
    def complete(self, service, seed_hits, intent=None, types=None, scope=None):
        from enterprise_data_context.models import SearchHit
        chosen={hit.path:hit for hit in seed_hits}
        frontier=list(seed_hits)
        max_hops=2 if intent in {"analysis_data_requirement","metric_to_models","impact_analysis"} else 1
        candidate_limit=max(8,len(seed_hits)*6)
        for _ in range(max_hops):
            next_frontier=[]
            for hit in frontier:
                page=service.pages[hit.path]
                candidates=[(r.get("target_path"),r.get("relation"),"reference",.75)
                    for r in page.references if r.get("status")=="CONFIRMED"]
                candidates += [(r.get("source"),r.get("relation"),"backref",.55)
                               for r in service.backrefs.get(hit.path,[])]
                for target,relation,origin,weight in candidates:
                    if len(chosen)>=candidate_limit:
                        break
                    if target in chosen or target not in service.pages or not relation_allowed(relation,intent):
                        continue
                    page=service.pages[target]
                    if not allowed_page(page,types,scope):
                        continue
                    selected=SearchHit(target,page.context_type,page.name,hit.score*weight,
                                       [origin+":"+relation],page.l0,page.l1)
                    chosen[target]=selected
                    next_frontier.append(selected)
            frontier=next_frontier
        return list(chosen.values())

    def rank(self, service, hits, seed_hits):
        from math import log1p
        if not hits:
            return []
        result=[]; covered=set(); types=set(); pool=list(hits)
        seed_ids={h.path for h in seed_hits}
        strongest=max(h.score for h in hits) or 1
        while pool:
            def utility(hit):
                page=service.pages[hit.path]
                aspects={k for k,v in page.coverage.items() if v}
                relevance=hit.score/strongest
                if not result:
                    return (hit.path in seed_ids,relevance,hit.path)
                gain=len(aspects-covered)
                density=gain/(1+log1p(len(page.l1))/10)
                return (True,relevance+.18*density+.12*(page.context_type not in types),hit.path)
            chosen=max(pool,key=utility)
            pool.remove(chosen); result.append(chosen)
            page=service.pages[chosen.path]
            covered.update(k for k,v in page.coverage.items() if v)
            types.add(page.context_type)
        return result
