"""Deterministic, evidence-preserving aggregate materialized views."""
from collections import Counter
from dataclasses import asdict
import json

from ..hierarchy_contracts import VIEWS
from ..indexes.hierarchy import values, fingerprint

SUMMARY_SECTIONS = {"primary_objects": "primary_objects", "core_metrics": "metrics",
                    "core_dimensions": "dimensions", "main_purposes": "analysis_purposes"}
TYPE_SECTIONS = {"business-object": "primary_objects", "metric": "core_metrics",
                 "dimension": "core_dimensions", "analysis-purpose": "main_purposes"}


def materialize_aggregate(index, path):
    node = index.nodes[path]
    views = {}
    for view in VIEWS:
        if not any(e["hierarchy_id"] == view for e in index.children[path]):
            continue
        members = sorted(index.descendants(path, view) & index.contexts.keys())
        member_set = set(members)
        subtree = index.descendants(path, view) | {path}
        relations = [e for e in index.edges if e["hierarchy_id"] == view and
                     e["parent_id"] in subtree and (e["child_id"] in subtree or e["status"] == "CANDIDATE")]
        frequencies = {k: Counter() for k in SUMMARY_SECTIONS}
        model_paths = {"logical_models": [], "physical_models": []}
        availability = Counter()
        evidence = []
        for p in members:
            c = index.contexts[p]
            for key, section in SUMMARY_SECTIONS.items():
                if c.section_status.get(section, "EXPLICIT") in {"EXPLICIT", "DERIVED"} and c.evidence.get(section):
                    frequencies[key].update(set(values(c.sections.get(section))))
            if c.context_type in TYPE_SECTIONS:
                frequencies[TYPE_SECTIONS[c.context_type]][c.name] += 1
            if c.context_type in {"logical-model", "physical-model"}:
                model_paths[c.context_type.replace("-model", "_models")].append(p)
                # Environment binding belongs to runtime overlays. A global aggregate
                # is reference-only regardless of stale matches on canonical records.
                availability["reference_only"] += 1
            for proofs in c.evidence.values():
                for e in proofs:
                    row = asdict(e)
                    if row not in evidence:
                        evidence.append(row)
        for edge in relations:
            for proof in edge["evidence"]:
                if proof not in evidence:
                    evidence.append(proof)
        summary = f"{node['name']}: {len(members)} reference contexts"
        l1 = {"summary": summary, **{k: [{"name": name, "count": count} for name, count in counter.most_common(12)] for k, counter in frequencies.items()},
              **{k: paths[:12] for k, paths in model_paths.items()},
              "model_counts": {k: len(v) for k, v in model_paths.items()},
              "child_groups": [{"path": e["child_id"], "name": index.nodes[e["child_id"]]["name"], "status": e["status"]}
                               for e in index.children[path] if e["active"] and e["hierarchy_id"] == view][:12],
              "environment_availability": {"status": "UNRESOLVED", "counts": dict(availability), "scope": "REFERENCE", "complete": False},
              "placement_counts": {s: sum(e["status"] == s for e in relations) for s in ("CONFIRMED", "DERIVED", "CANDIDATE")},
              "member_count": len(members), "partial_source_coverage": True,
              "truncated": any(len(c) > 12 for c in frequencies.values()) or any(len(v) > 12 for v in model_paths.values()) or sum(e["active"] and e["hierarchy_id"] == view for e in index.children[path]) > 12}
        l0 = summary + "; " + "; ".join(k + ": " + ", ".join(list(counter)[:4]) for k, counter in frequencies.items() if counter)
        l2 = {"members": members, "relations": relations, "evidence": evidence,
              "hierarchy_provenance": [e["provenance"] for e in relations],
              "classification_conflicts": [c for c in index.conflicts if c["child_id"] in member_set and c["hierarchy_id"] == view],
              "canonical_conflicts": [{"context":p, **conflict} for p in members for conflict in index.contexts[p].conflicts],
              "unclassified_members": [p for p in members if index.classification(p)["status"] == "unclassified"],
              "partially_classified_members": [p for p in members if index.classification(p)["status"] == "partially_classified"],
              "candidate_placements": [e for e in relations if e["status"] == "CANDIDATE"]}
        views[view] = {"L0": l0[:800], "L1": l1, "L2": l2}
    return {"path": path, "kind": "aggregate-context", "name": node["name"],
            "L0": " | ".join(v["L0"] for v in views.values())[:1200], "views": views,
            "member_fingerprints": {p: fingerprint(asdict(index.contexts[p])) for p in sorted(index.descendants(path) & index.contexts.keys())}}


def read_aggregate(index, path, level="L1", sections=None, view=None):
    page = index.aggregate_pages[path]
    level = level.upper()
    if level not in {"L0", "L1", "L2"}:
        raise ValueError("invalid aggregate disclosure level")
    views = {v: content[level] for v, content in page["views"].items() if view is None or v == view}
    if sections and level == "L2":
        views = {v: {k: val for k, val in content.items() if k in sections} for v, content in views.items()}
    return {"path": path, "level": level, "context_type": "aggregate-context",
            "knowledge_layer": "REFERENCE", "content": views, "hierarchy_views": list(views)}
