"""External hierarchy policy loading. Domain values belong to configuration."""
from copy import deepcopy
import json
from pathlib import Path

from .hierarchy_contracts import (SOURCE_PRIORITY, VIEWS, VERSION, APPLICABLE_VIEWS,
    MATERIALIZATION_VERSION, ROUTING_VERSION, AGGREGATE_INDEX_VERSION)


def load_hierarchy_config(path=None):
    return validate_hierarchy_config(json.loads(Path(path).read_text()) if path else {"version": VERSION})


def validate_hierarchy_config(value):
    config = deepcopy(value)
    if not isinstance(config, dict) or not config.get("version"):
        raise ValueError("hierarchy config requires a version")
    for key in ("hierarchy_enabled", "inference_enabled", "llm_enabled"):
        if key in config and not isinstance(config[key], bool):
            raise ValueError(f"{key} must be boolean")
    for key in ("confidence_threshold", "ambiguity_margin"):
        v = config.get(key, .8 if key == "confidence_threshold" else .15)
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not 0 <= v <= 1:
            raise ValueError(f"invalid {key}")
    for key in ("candidate_limit", "max_neighbors", "branch_k", "max_llm_calls", "max_input_characters", "important_element_limit"):
        if key in config and (type(config[key]) is not int or config[key] < 1):
            raise ValueError(f"{key} must be a positive integer")
    for v in config.get("feature_weights", {}).values():
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not 0 <= v <= 1:
            raise ValueError("feature weights must be in 0..1")
    ids, aliases = set(), {}
    for label in config.get("taxonomy", []):
        if not isinstance(label, dict) or not label.get("id") or label["id"] in ids:
            raise ValueError("duplicate or missing taxonomy id")
        if label.get("view") not in VIEWS or label.get("kind") not in VIEWS[label["view"]] or not label.get("label"):
            raise ValueError("invalid taxonomy kind/view/label")
        ids.add(label["id"])
        for name in [label["label"], *label.get("aliases", [])]:
            key = (label["view"], label["kind"], name.casefold())
            if key in aliases and aliases[key] != label["id"]:
                raise ValueError("taxonomy alias collision")
            aliases[key] = label["id"]
    for mapping in config.get("tag_mappings", []):
        if (not mapping.get("tag") or not mapping.get("rule_id") or mapping.get("view") not in VIEWS or
                mapping.get("kind") not in VIEWS[mapping["view"]] or not mapping.get("label")):
            raise ValueError("invalid tag mapping")
    for slot in config.get("exclusive_slots", []):
        if slot.get("view") not in VIEWS or slot.get("kind") not in VIEWS[slot["view"]]:
            raise ValueError("invalid exclusive slot")
    rule_ids = set()
    for rule in config.get("rules", []):
        if not rule.get("id") or rule["id"] in rule_ids or rule.get("selected") not in ids or not rule.get("when"):
            raise ValueError("invalid hierarchy rule")
        confidence = rule.get("confidence", .95)
        if isinstance(confidence,bool) or not isinstance(confidence,(float,int)) or not 0 <= confidence <= 1:
            raise ValueError("invalid rule confidence")
        rule_ids.add(rule["id"])
        if rule.get("source_priority", "grain_dimension_metric") not in SOURCE_PRIORITY:
            raise ValueError("invalid rule source priority")
    matrix = {**APPLICABLE_VIEWS, **config.get("applicable_views", {})}
    for kind, views in matrix.items():
        if (kind not in APPLICABLE_VIEWS or not isinstance(views, list) or not views or
                len(set(views)) != len(views) or any(v not in APPLICABLE_VIEWS[kind] for v in views)):
            raise ValueError("invalid applicable_views")
    config["applicable_views"] = matrix
    config.setdefault("routing_policy_version", ROUTING_VERSION)
    config.setdefault("aggregate_materialization_version", MATERIALIZATION_VERSION)
    config.setdefault("aggregate_index_version", AGGREGATE_INDEX_VERSION)
    if config.get("branch_retrieval", "hybrid") not in {"lexical", "hybrid"}:
        raise ValueError("invalid branch_retrieval")
    # Candidate branches are excluded from strong recall in this release.
    if config.get("candidate_branch_weight", 0) != 0:
        raise ValueError("candidate_branch_weight must be zero in V1.1")
    nodes = {}
    names = set()
    for node in config.get("taxonomy_nodes", []):
        if (not isinstance(node, dict) or not node.get("id") or node["id"] in nodes or
                node.get("view") not in VIEWS or node.get("kind") not in VIEWS[node["view"]] or
                not isinstance(node.get("label"), str) or not node["label"]):
            raise ValueError("invalid taxonomy node")
        if node["view"] not in matrix[node["kind"]]:
            raise ValueError("entity_placed_in_non_applicable_view")
        for label in [node["label"], *node.get("aliases", [])]:
            key = (node["view"], node["kind"], label.casefold())
            if key in names:
                raise ValueError("taxonomy alias collision")
            names.add(key)
        nodes[node["id"]] = node
    outgoing = {key: set() for key in nodes}
    for edge in config.get("taxonomy_edges", []):
        if not isinstance(edge, dict):
            raise ValueError("invalid_taxonomy_edge")
        parent, child = edge.get("parent"), edge.get("child")
        if parent not in nodes or child not in nodes:
            raise ValueError("unknown_taxonomy_node")
        provenance = edge.get("provenance", {})
        proofs = edge.get("evidence", [])
        if (parent == child or nodes[parent]["view"] != nodes[child]["view"] or
                edge.get("status") != "CONFIRMED" or provenance.get("method") != "explicit_taxonomy" or
                not provenance.get("source") or not proofs or
                any(not isinstance(e, dict) or not e.get("source", {}).get("source_id") or
                    not e.get("source", {}).get("path") for e in proofs)):
            raise ValueError("invalid_taxonomy_edge")
        outgoing[parent].add(child)
    pending, done = set(), set()
    def visit(node):
        if node in pending:
            raise ValueError("taxonomy_cycle")
        if node in done:
            return
        pending.add(node)
        for child in outgoing[node]:
            visit(child)
        pending.remove(node); done.add(node)
    for node in nodes:
        visit(node)
    return config
