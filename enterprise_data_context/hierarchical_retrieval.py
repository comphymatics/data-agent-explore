"""One serving operation performs branch recall, rich read and anchor discovery."""
from time import perf_counter

from .hierarchy_contracts import VIEWS
from .indexes.page import FACET_ALIASES, facet_matches
from .models import SearchHit
from .serving import allowed_page
from .materialization.aggregate_pages import read_aggregate


def route(service, query, mode="auto", hierarchy=None, intent=None, scope=None, retrieval_strategy=None):
    if mode not in {"auto", "direct", "hierarchical", "hybrid"}:
        raise ValueError("invalid retrieval mode")
    if hierarchy is not None and hierarchy not in VIEWS:
        raise ValueError("invalid hierarchy view")
    from .indexes.mention import ExactMentionResolver
    result = ExactMentionResolver(service.pidx, service.eidx).resolve(query,
        service.hierarchy.config["hierarchy_retrieval"]["max_entities_examined_per_branch"])
    page_anchors, element_paths = set(), set()
    for mention in result["mentions"]:
        for target in mention["targets"]:
            if target["entity_type"] in {"metric", "dimension", "logical-model", "physical-model"} and mention["source"] == "page":
                page_anchors.add(target["parent_page"])
            elif mention["source"] == "element" and target["element_type"] in {"Field", "Attribute", "Counter", "Formula", "JoinKey"}:
                element_paths.add(target["parent_page"])
    page_anchors = sorted(page_anchors)
    exact = set(page_anchors) | element_paths
    from .retrieval_strategy import strategy
    anchor_types = [service.pages[p].context_type for p in page_anchors if p in service.pages]
    if element_paths:
        anchor_types.append("field")
    if exact and not anchor_types:
        anchor_types.append("stable-id")
    decision = strategy(query, intent, scope, anchor_types, mode=mode, hierarchy=hierarchy, preferred=retrieval_strategy)
    if not service.hierarchy.config.get("hierarchy_enabled", True):
        decision.update(mode="direct", hierarchy_views=[], primary_view=None)
        decision["reasons"].append("hierarchy_disabled")
    initial = {"mode": decision["mode"], "views": list(decision["hierarchy_views"]), "confidence": decision["confidence"]}
    arbitration = {"triggered": False, "view_scores": {}}
    recalled = None
    config = service.hierarchy.config["view_arbitration"]
    if (decision["mode"] != "direct" and not exact and hierarchy is None and config["enabled"] and
            decision["confidence"] < config["confidence_threshold"]):
        arbitration["triggered"] = True
        started = perf_counter()
        recalled = []
        for view in VIEWS:
            rows = service.hierarchy.aggregate_index.search(query, [view], top_k=config["branch_k"], scope=scope)
            recalled.extend(rows)
            # RRF normalized by channel mass avoids raw BM25 scale differences.
            scores = [r["score"] for r in rows]
            score = (max(scores, default=0) * .7 + sum(scores)/max(1, len(scores)) * .3)
            # Small prior resolves channel-rank ties; it cannot create evidence.
            if view == initial["views"][0] and scores:
                score *= 1.1
            arbitration["view_scores"][view] = score
        ranked_views = sorted(VIEWS, key=lambda v: (-arbitration["view_scores"][v], v))
        best = arbitration["view_scores"][ranked_views[0]]
        if best > 0:
            selected_views = [v for v in ranked_views if arbitration["view_scores"][v] >= best*.8][:config["max_views"]]
            decision.update(hierarchy_views=selected_views, primary_view=selected_views[0])
            decision["reasons"].append("aggregate_cross_view_arbitration")
        else:
            arbitration["fallback"] = "no_relevant_aggregate_evidence"
        arbitration["latency_ms"] = (perf_counter()-started)*1000
    return {**decision, "retrieval_strategy": decision,
            "mention_resolution": {**result["diagnostics"], "mentions": result["mentions"]},
            "routing": {"initial": initial, "arbitration": arbitration,
                        "final": {"mode": decision["mode"], "primary_view": decision["primary_view"], "views": decision["hierarchy_views"]}},
            "view_arbitration": arbitration, "_arbitrated_rows": recalled, "hierarchy_view": decision["primary_view"],
            "exact_anchor_ids": sorted(exact), "page_anchor_ids": page_anchors, "element_anchor_ids": sorted(element_paths),
            "selected_branches": [], "hierarchy_contexts": [], "branch_candidates": [],
            "fallback": None, "version": "hierarchical-serving/v1.2"}


def discover(service, query, trace, seed_hits, top_k, types=None, scope=None):
    """Rank L0 branches then bound member discovery; no per-node tool call."""
    index = service.hierarchy
    selected = {h.path: h for h in seed_hits}
    for path in trace["exact_anchor_ids"]:
        page = service.pages.get(path)
        if page and allowed_page(page, types, scope):
            selected[path] = SearchHit(path, page.context_type, page.name,
                max([h.score for h in seed_hits] or [.05]) * (1.5 if path in trace["page_anchor_ids"] or not trace["page_anchor_ids"] else .6),
                ["exact_element_anchor" if path in trace["element_anchor_ids"] else "exact_semantic_anchor"], page.l0, page.l1)
    if trace["mode"] == "direct":
        trace.pop("_arbitrated_rows", None)
        return sorted(selected.values(), key=lambda h: (-h.score, h.path))[:top_k]
    views = trace["hierarchy_views"]
    budget = index.config["hierarchy_retrieval"]
    branch_k = budget["branch_k"]
    started = perf_counter()
    recalled = trace.pop("_arbitrated_rows", None)
    rows = (sorted((r for r in recalled if r["hierarchy_view"] in views), key=lambda r: (-r["score"], r["path"]))
            if recalled is not None else index.aggregate_index.search(query, views, top_k=branch_k * 3,
                method=index.config.get("branch_retrieval", "hybrid"), scope=scope))
    trace["branch_recall_latency_ms"] = (perf_counter()-started)*1000
    trace["branch_candidates"] = rows[:branch_k*3]
    trace["branch_warnings"] = index.aggregate_index.last_warnings
    trace["branch_budget"] = {**budget, "branches": [], "examined_members": 0}
    base = max([h.score for h in seed_hits] or [.05])
    for row in rows[:branch_k]:
        path, view = row["path"], row["hierarchy_view"]
        members = index.branch_membership[path]
        started = perf_counter()
        hits = service.pidx.search(query, types=types, top_k=budget["entity_candidate_k"],
            candidate_limit=budget["max_entities_examined_per_branch"], allowed_paths=members,
            fallback_paths=index.branch_previews[path])
        examined = service.pidx.last_examined_count
        trace["branch_budget"]["examined_members"] += examined
        trace["branch_budget"]["branches"].append({"path": path, "branch_size": len(members),
            "examined_members": examined, "candidate_count": len(hits),
            "posting_reads": service.pidx.last_candidate_diagnostics["posting_reads"],
            "entity_retrieval_latency_ms": (perf_counter()-started)*1000,
            "truncated": len(members) > examined})
        eligible = [hit for hit in hits if organization_allowed_page(service, hit.path, types, scope)]
        if not eligible:
            continue
        trace["selected_branches"].append(path)
        trace["hierarchy_contexts"].append(read_aggregate(index, path, "L1", view=view))
        for rank, hit in enumerate(eligible):
            old = selected.get(hit.path)
            score = base*(.9 + .1/(rank+1))
            if old:
                score = max(score, old.score) + base*.2
            selected[hit.path] = SearchHit(hit.path, hit.context_type, hit.name, score,
                list(dict.fromkeys((old.reasons if old else []) + hit.reasons + ["hierarchy:" + view])), hit.l0, hit.l1)
    if not trace["selected_branches"]:
        trace["fallback"] = "no_supported_branch"
    return sorted(selected.values(), key=lambda h: (-h.score, h.path))[:budget["entity_candidate_k"]]


def organization_allowed_page(service, path, types, scope):
    """Explicit and rule-derived organization may satisfy a navigation scope.

    Candidates never satisfy hard filters. Canonical facets are left untouched.
    """
    page = service.pages[path]
    remaining = dict(scope or {})
    if page.context_type in {"logical-model", "physical-model"}:
        ancestors = service.hierarchy.ancestors(path)
        for key, expected in list(remaining.items()):
            facet = FACET_ALIASES.get(key, key)
            kind = {"topic_domain": "topic-domain", "topic": "topic", "layer": "layer"}.get(facet)
            if kind and not page.facets.get(facet) and any(service.hierarchy.nodes[p]["kind"] == kind and facet_matches(service.hierarchy.nodes[p]["name"], expected) for p in ancestors):
                remaining.pop(key)
    return allowed_page(page, types, remaining)
