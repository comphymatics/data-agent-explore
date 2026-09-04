from __future__ import annotations

from collections import defaultdict
from urllib.parse import quote


MODEL_TYPES = {"logical-model", "physical-model"}


class HierarchyIndex:
    """Derived browse hierarchy over canonical contexts and governed model facets."""

    def __init__(self):
        self.nodes: dict[str, dict] = {}
        self.parents: dict[str, list[dict]] = defaultdict(list)
        self.children: dict[str, list[dict]] = defaultdict(list)

    def project(self, contexts):
        contexts = list(contexts)
        for context in contexts:
            if context.identity_status not in {"INFERRED", "CANDIDATE"}:
                self._add_context(context)

        for context in contexts:
            if context.path not in self.nodes:
                continue
            self._add_declared_parents(context)
            if context.context_type in MODEL_TYPES:
                self._add_model_classification(context)
        return self

    def _add_context(self, context):
        self.nodes[context.path] = {
            "path": context.path,
            "name": context.name,
            "kind": context.context_type,
            "virtual": False,
            "facets": {
                key: context.sections[key]
                for key in (
                    "semantic_role", "scenario.kind", "application",
                    "classification.layer", "topic_domain", "topic",
                )
                if context.sections.get(key) not in (None, "", [], {})
            },
        }

    def _add_declared_parents(self, context):
        for reference in context.references:
            if (
                reference.status == "CONFIRMED"
                and reference.target_path in self.nodes
                and reference.relation == "part_of"
            ):
                self.add_edge(
                    reference.target_path,
                    context.path,
                    relation="contains",
                    source_relation=reference.relation,
                    assertion_status="EXPLICIT",
                )

        if context.context_type != "physical-model":
            return
        for reference in context.references:
            if (
                reference.status == "CONFIRMED"
                and reference.target_path in self.nodes
                and reference.relation == "implements_logical_model"
            ):
                self.add_edge(
                    reference.target_path,
                    context.path,
                    relation="realized_by",
                    source_relation=reference.relation,
                    assertion_status="EXPLICIT",
                )

    def _add_model_classification(self, context):
        parts = []
        for kind, section in (
            ("layer", "classification.layer"),
            ("domain", "topic_domain"),
            ("topic", "topic"),
        ):
            value = context.sections.get(section)
            if value not in (None, "", [], {}):
                parts.append((kind, section, str(value)))

        parent_path = None
        accumulated = []
        for kind, section, value in parts:
            accumulated.append(value)
            path = hierarchy_path("models", *accumulated)
            self.nodes.setdefault(path, {
                "path": path,
                "name": value,
                "kind": kind,
                "virtual": True,
                "facets": {kind: value},
            })
            if parent_path:
                self.add_edge(
                    parent_path,
                    path,
                    relation="contains",
                    source_relation="classification",
                    assertion_status=context.section_status.get(section, "EXPLICIT"),
                )
            parent_path = path

        if parent_path:
            terminal_section = parts[-1][1]
            self.add_edge(
                parent_path,
                context.path,
                relation="classifies",
                source_relation=terminal_section,
                assertion_status=context.section_status.get(terminal_section, "EXPLICIT"),
            )

    def add_edge(
        self,
        parent_path,
        child_path,
        *,
        relation,
        source_relation,
        assertion_status,
    ):
        if parent_path == child_path or parent_path not in self.nodes or child_path not in self.nodes:
            return
        edge = {
            "source": parent_path,
            "relation": relation,
            "target": child_path,
            "source_relation": source_relation,
            "assertion_status": assertion_status,
        }
        if edge not in self.children[parent_path]:
            self.children[parent_path].append(edge)
            self.parents[child_path].append(edge)

    def has(self, path):
        return path in self.nodes

    def describe(self, path):
        if path not in self.nodes:
            return {}
        return {
            "node": dict(self.nodes[path]),
            "breadcrumb": self._breadcrumb(path),
            "parents": [self._edge_with_node(edge, parent=True) for edge in self.parents[path]],
            "children": [self._edge_with_node(edge, parent=False) for edge in self.children[path]],
        }

    def _edge_with_node(self, edge, *, parent):
        node_path = edge["source"] if parent else edge["target"]
        return {**edge, "node": dict(self.nodes[node_path])}

    def _breadcrumb(self, path):
        trail = []
        current = path
        seen = set()
        while current in self.nodes and current not in seen:
            seen.add(current)
            trail.append(dict(self.nodes[current]))
            incoming = sorted(
                self.parents[current],
                key=lambda edge: (
                    not self.nodes[edge["source"]].get("virtual", False),
                    edge["source"],
                ),
            )
            if not incoming:
                break
            current = incoming[0]["source"]
        return list(reversed(trail))

    @property
    def edge_count(self):
        return sum(len(edges) for edges in self.children.values())


def hierarchy_path(namespace, *parts):
    encoded = "/".join(quote(str(part), safe="") for part in parts)
    return f"hierarchy://{namespace}/{encoded}"
