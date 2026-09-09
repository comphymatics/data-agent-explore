from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy

from .indexes.hierarchy import HierarchyIndex


class SemanticOrganizationBuilder:
    """Build derived hierarchy views and an auditable association coverage report."""

    def __init__(self, config=None, provider=None):
        self.config, self.provider = config, provider

    def build(self, contexts, previous=None):
        contexts = list(contexts)
        hierarchy = (deepcopy(previous, {id(previous.aggregate_index.encoder.encoder):previous.aggregate_index.encoder.encoder})
                     if previous is not None else HierarchyIndex(self.config, self.provider))
        hierarchy.config = self.config or hierarchy.config
        hierarchy.provider = self.provider
        hierarchy.update(contexts)
        return {
            "hierarchy": hierarchy,
            "association_report": association_report(contexts, hierarchy),
        }


def association_report(contexts, hierarchy=None):
    contexts = list(contexts)
    by_path = {context.path: context for context in contexts}
    status_counts = Counter()
    relation_status = defaultdict(Counter)
    confirmed_paths = set()
    cross_source = []

    for context in contexts:
        for reference in context.references:
            status_counts[reference.status] += 1
            relation_status[reference.relation][reference.status] += 1
            if reference.status != "CONFIRMED" or not reference.target_path:
                continue
            confirmed_paths.update((context.path, reference.target_path))
            target = by_path.get(reference.target_path)
            if target is None:
                continue
            source_ids = sorted(_context_source_ids(context))
            target_source_ids = sorted(_context_source_ids(target))
            if source_ids and target_source_ids and set(source_ids).isdisjoint(target_source_ids):
                cross_source.append({
                    "source": context.path,
                    "relation": reference.relation,
                    "target": reference.target_path,
                    "source_ids": source_ids,
                    "target_source_ids": target_source_ids,
                })

    active_paths = {
        context.path for context in contexts
        if context.identity_status not in {"INFERRED", "CANDIDATE"}
    }
    hierarchy = hierarchy or HierarchyIndex().project(contexts)
    return {
        "context_count": len(contexts),
        "reference_count": sum(status_counts.values()),
        "references_by_status": dict(sorted(status_counts.items())),
        "references_by_relation": {
            relation: dict(sorted(counts.items()))
            for relation, counts in sorted(relation_status.items())
        },
        "cross_source_confirmed_count": len(cross_source),
        "cross_source_confirmed": cross_source,
        "orphan_context_count": len(active_paths - confirmed_paths),
        "orphan_contexts": sorted(active_paths - confirmed_paths),
        "hierarchy_node_count": len(hierarchy.nodes),
        "hierarchy_edge_count": hierarchy.edge_count,
    }


def _context_source_ids(context):
    source_ids = {
        evidence.source.source_id
        for evidence_rows in context.evidence.values()
        for evidence in evidence_rows
        if evidence.source.source_id
    }
    source_ids.update(
        evidence.source.source_id
        for reference in context.references
        for evidence in reference.evidence
        if evidence.source.source_id
    )
    material_sources = {
        source_id for source_id in source_ids
        if not source_id.startswith(("modeling-standard:", "governance:"))
    }
    return material_sources or source_ids
