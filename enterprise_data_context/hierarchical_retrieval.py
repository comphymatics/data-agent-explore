"""One serving operation performs branch recall, rich read and anchor discovery."""
import math
import re

from .hierarchy_contracts import VIEWS
from .indexes.page import toks, FACET_ALIASES, facet_matches
from .models import SearchHit
from .serving import allowed_page
from .materialization.aggregate_pages import read_aggregate


def contains_identifier(query, key):
    key = str(key).strip().casefold()
    if len(key) < 2:
        return query.strip().casefold() == key
    # ASCII identifiers next to Chinese grammar are still exact anchors.
    return bool(key and re.search(r"(?<![a-z0-9_])" + re.escape(key) + r"(?![a-z0-9_])", query.casefold()))


def route(service, query, mode="auto", hierarchy=None, intent=None):
    if mode not in {"auto", "direct", "hierarchical", "hybrid"}:
        raise ValueError("invalid retrieval mode")
    if hierarchy is not None and hierarchy not in VIEWS:
        raise ValueError("invalid hierarchy view")
    exact = set()
    for key, paths in service.pidx.exact.items():
        if contains_identifier(query, key):
            exact.update(p for p in paths if service.pages[p].context_type in {"metric", "dimension", "logical-model", "physical-model"})
    for p, c in service.contexts.items():
        if contains_identifier(query, c.path) or any(contains_identifier(query, v) for k, v in c.identity_hints.items() if k in {"stable_id", "strong_key"}):
            exact.add(p)
    page_anchors = sorted(exact)
    element_paths = set()
    # Element records remain in ElementIndex, never promoted to pages.
    for key, ids in service.eidx.exact.items():
        if contains_identifier(query, key):
            element_paths.update(service.eidx.records[i]["path"] for i in ids
                                 if service.eidx.records[i]["kind"] in {"Field", "Attribute", "Counter", "Formula", "JoinKey"})
    exact.update(element_paths)
    cross = any(word in query.casefold() for word in ("还需要", "跨域", "结合", "what else", "across domains"))
    selected = mode
    if selected == "auto":
        selected = "hybrid" if exact and cross else "direct" if exact else "hierarchical"
    if not service.hierarchy.config.get("hierarchy_enabled", True):
        selected = "direct"
    view = hierarchy
    if selected in {"hierarchical", "hybrid"} and view is None:
        if any(word in query.casefold() for word in ("主题", "业务对象", "domain", "topic")):
            view = "domain"
        elif any(word in query.casefold() for word in ("数仓", "分层", "ods", "asset")):
            view = "asset"
        else:
            view = "analysis"
    return {"mode": selected, "hierarchy_view": view if selected != "direct" else None,
            "exact_anchor_ids": sorted(exact), "page_anchor_ids": page_anchors, "element_anchor_ids": sorted(element_paths),
            "selected_branches": [], "hierarchy_contexts": [], "branch_candidates": [],
            "fallback": None, "version": "hierarchical-serving/v1"}


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
        return sorted(selected.values(), key=lambda h: (-h.score, h.path))[:top_k]
    q = set(toks(query))
    rows = []
    view = trace["hierarchy_view"]
    for path in sorted(index.recall_branches(q, view)):
        aggregate = index.aggregate_pages[path]
        content = aggregate["views"].get(view)
        if not content:
            continue
        overlap = q & index.aggregate_terms[path][view]
        if not overlap:
            continue
        # Root hubs get less weight than discriminative, compact branches.
        name_overlap = len(q & set(toks(aggregate["name"])))
        l1 = content["L1"]
        rich_overlap = len(q & set(toks(str(l1))))
        score = (len(overlap) + 2 * name_overlap + .15 * rich_overlap) / (1 + math.log1p(l1["member_count"]) * .2)
        rows.append((score, path))
    rows.sort(key=lambda x: (-x[0], x[1]))
    branch_k = index.config.get("branch_k", 3)
    trace["branch_candidates"] = [{"path": p, "score": s} for s, p in rows[:branch_k * 3]]
    branch_members = {}
    for score, path in rows[:branch_k]:
        content = index.aggregate_pages[path]["views"][view]
        members = content["L2"]["members"]
        if path in service.pages:
            members = [path, *members]
        eligible = [p for p in members if p in service.pages and organization_allowed_page(service, p, types, scope)]
        if not eligible:
            continue
        trace["selected_branches"].append(path)
        trace["hierarchy_contexts"].append(read_aggregate(index, path, "L1", view=view))
        for p in eligible:
            branch_members[p] = max(branch_members.get(p, 0), score)
    if not branch_members:
        trace["fallback"] = "no_supported_branch"
    # The existing hybrid retrieval is reused for entity relevance; branch membership
    # supplies anchors that the original query vocabulary could not retrieve.
    base = max([h.score for h in seed_hits] or [.05])
    strongest = max(branch_members.values(), default=1)
    for path, branch_score in branch_members.items():
        page = service.pages[path]
        lexical = len(q & set(toks(page.l0 + " " + page.l1))) / max(1, len(q))
        score = base * (.7 + .2 * branch_score / strongest + .1 * lexical)
        old = selected.get(path)
        if old:
            score = max(score, old.score) + base * .2
        selected[path] = SearchHit(path, page.context_type, page.name, score,
                                  list(dict.fromkeys((old.reasons if old else []) + ["hierarchy:" + view])), page.l0, page.l1)
    return sorted(selected.values(), key=lambda h: (-h.score, h.path))[:max(top_k, top_k * 2)]


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
