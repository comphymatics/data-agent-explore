from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from dataclasses import asdict
from hashlib import sha256
import json
from urllib.parse import quote, unquote

from ..hierarchy_contracts import HierarchyEdge, STATUS_RANK, VIEWS, VERSION, edge_errors

MODEL_TYPES = {"logical-model", "physical-model"}
# Only explicit semantic relations can supply organization. Lineage is excluded.
RELATION_VIEWS = {
    "part_of": (("domain", "reverse"), ("analysis", "reverse")),
    "implements_logical_model": tuple((v, "reverse") for v in VIEWS),
    "has_purpose": (("analysis", "forward"),),
    "uses_metric": (("analysis", "forward"),),
    "requires_metric": (("analysis", "forward"),),
    "uses_dimension": (("analysis", "forward"),),
    "requires_dimension": (("analysis", "forward"),),
    "uses_model": (("analysis", "forward"),),
    "provides_metric": (("analysis", "reverse"),),
    "maps_to_business_object": (("domain", "reverse"), ("analysis", "reverse")),
}
SECTION_VIEWS = {
    "analysis": (("scenarios", "scenario"), ("analysis_purposes", "analysis-purpose"),
                 ("metrics", "metric"), ("dimensions", "dimension"), ("primary_objects", "business-object")),
    "domain": (("business_category", "business-category"), ("data_domain", "data-domain"),
               ("topic_domain", "topic-domain"), ("topic", "topic"), ("primary_objects", "business-object")),
    "asset": (("classification.layer", "layer"),),
}


def hierarchy_path(namespace, *parts):
    """Legacy URI helper retained for callers; new projections use view_path."""
    return f"hierarchy://{namespace}/" + "/".join(quote(str(p), safe="") for p in parts)


def view_path(view, kind, name):
    return f"data://views/{view}/{kind}/" + quote(str(name), safe="")


def values(value):
    if value in (None, "", [], {}):
        return []
    if isinstance(value, list):
        return [s for v in value for s in values(v)]
    if isinstance(value, dict):
        if value.get("status", "EXPLICIT") not in {"EXPLICIT", "CONFIRMED", "DERIVED"}:
            return []
        return values(value.get("name", value.get("value", value.get("label"))))
    return [str(value)]


def fingerprint(value):
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


class HierarchyIndex:
    """One multiview organization projection, with independently governed edges."""

    def __init__(self, config=None, provider=None):
        from ..hierarchy_config import validate_hierarchy_config
        self.config = validate_hierarchy_config(config or {"version": VERSION})
        self.provider = provider
        self.nodes = {}
        self.parents = defaultdict(list)
        self.children = defaultdict(list)
        self.edges = []
        self.contributions = {}
        self.contexts = {}
        self.aggregate_pages = {}
        self.aggregate_terms = {}
        self.branch_membership = {}
        self.branch_previews = {}
        self.branch_postings = {v: defaultdict(set) for v in VIEWS}
        self.dependencies = {}
        self.inference_audit = {}
        self.build_issues = {}
        self.conflicts = []
        self.last_update = {}
        self.history = []

    def project(self, contexts):
        return self.update(contexts)

    def update(self, contexts):
        """Fingerprint changes; infer only changed entities and affected semantic neighbors."""
        from ..hierarchy_inference import OverlayClassifier, neighbor_dependencies
        from ..materialization.aggregate_pages import materialize_aggregate
        from ..hierarchy_config import validate_hierarchy_config
        self.config = validate_hierarchy_config(self.config)
        current = {c.path: c for c in contexts if c.identity_status not in {"INFERRED", "CANDIDATE"}}
        hashes = {p: fingerprint(asdict(c)) for p, c in current.items()}
        previous_hashes = getattr(self, "_hashes", {})
        config_hash = fingerprint(self.config)
        changed = {p for p in set(previous_hashes) | set(hashes) if previous_hashes.get(p) != hashes.get(p)}
        inference_config = {k: v for k, v in self.config.items() if k not in {
            "taxonomy_nodes", "taxonomy_edges", "routing_policy_version", "aggregate_materialization_version",
            "aggregate_index_version", "branch_retrieval", "branch_k", "hierarchy_enabled", "candidate_branch_weight",
            "hierarchy_retrieval", "view_arbitration", "mention_index_version", "hardening_version", "taxonomy_transitions"}}
        inference_hash = fingerprint(inference_config)
        if inference_hash != getattr(self, "_inference_hash", None):
            changed |= set(current)
        old_taxonomy = deepcopy(self.contributions.get("@taxonomy", {"nodes": {}, "edges": []}))
        taxonomy_hash = fingerprint([self.config.get("taxonomy_nodes", []), self.config.get("taxonomy_edges", [])])
        taxonomy_changed = taxonomy_hash != getattr(self, "_taxonomy_hash", None)
        if taxonomy_changed:
            # Only contributors using changed governed names require reprojection.
            old_labels = getattr(self, "_taxonomy_labels", [])
            labels = self.config.get("taxonomy_nodes", [])
            changed_labels = [n for n in old_labels if n not in labels] + [n for n in labels if n not in old_labels]
            from ..hierarchy_inference import values
            names = {name.casefold() for n in changed_labels for name in [n["label"], *n.get("aliases", [])]}
            for p, c in current.items():
                source_labels = [v for sections in SECTION_VIEWS.values() for section, _ in sections for v in values(c.sections.get(section))]
                tags = c.sections.get("tags", [])
                source_labels.extend(v for tag in (tags if isinstance(tags, list) else [tags]) for v in values(tag))
                if names.intersection(v.casefold() for v in source_labels):
                    changed.add(p)
            governed_paths = {p for p, node in self.nodes.items() if node["name"].casefold() in names}
            for owner, contribution in self.contributions.items():
                if owner in current and any(e["parent_id"] in governed_paths or e["child_id"] in governed_paths
                                            for e in contribution["edges"]):
                    changed.add(owner)
        old_deps = self.dependencies
        new_deps = neighbor_dependencies(current, self.config)
        affected = set(changed)
        for path in changed:
            affected.update(old_deps.get(path, []))
            affected.update(new_deps.get(path, []))
        old_endpoints = {n for p in affected for e in self.contributions.get(p, {}).get("edges", []) for n in (e["parent_id"], e["child_id"])}
        old_ancestors = set(affected) | old_endpoints
        for p in list(old_ancestors):
            old_ancestors.update(self.ancestors(p))
        old_taxonomy_ancestors = {e["parent_id"]: self.ancestors(e["parent_id"]) for e in old_taxonomy["edges"]}
        old_nodes = deepcopy(self.nodes)
        self.contexts = current
        self.nodes = {p: {"path": p, "name": c.name, "kind": c.context_type, "virtual": False,
                          "facets": {k: c.sections[k] for k in ("topic_domain", "topic", "classification.layer") if k in c.sections}}
                      for p, c in current.items()}
        self._name_index = defaultdict(list)
        for c in current.values():
            for name in [c.name, *c.aliases]:
                self._name_index[(c.context_type, name.casefold())].append(c.path)
        self.build_issues = {p: v for p, v in self.build_issues.items() if p not in affected}
        for path in sorted(affected):
            if path in self.contributions:
                self.history.append({"context": path, "previous_fingerprint": previous_hashes.get(path),
                    "reason": "source_or_dependency_changed", "contribution": deepcopy(self.contributions[path]),
                    "inference_audit": deepcopy(self.inference_audit.get(path))})
            self.contributions.pop(path, None)
            self.inference_audit.pop(path, None)
        # Restore nodes owned by unchanged contributors. No LLM is called here.
        for owner, record in self.contributions.items():
            if owner != "@taxonomy":
                self.nodes.update(deepcopy(record["nodes"]))
        self._taxonomy_lookup = {}
        self._build_taxonomy(old_taxonomy)
        for path in sorted(affected & current.keys()):
            self._build_context(current[path])
        self._reindex()
        classifier = OverlayClassifier(self.config, self.provider)
        if self.config.get("inference_enabled", True):
            # A frozen deterministic backbone prevents inference cascades/order dependence.
            backbone = deepcopy(self.edges)
            for path in sorted(affected & current.keys()):
                if current[path].context_type not in MODEL_TYPES:
                    continue
                placements, audit = classifier.classify(current[path], current, backbone)
                self.inference_audit[path] = audit
                for placement in placements:
                    self._add_placement(current[path], **placement)
        self._reindex()
        # Prune orphan virtual nodes after reclassification/deletion.
        endpoints = {p for e in self.edges for p in (e["parent_id"], e["child_id"])}
        self.nodes = {p: n for p, n in self.nodes.items() if not n["virtual"] or p in endpoints or p in self.contributions["@taxonomy"]["nodes"]}
        def edge_key(edge):
            return fingerprint({k: v for k, v in edge.items() if k != "created_at"})
        new_taxonomy = self.contributions["@taxonomy"]
        old_keys = {edge_key(e) for e in old_taxonomy["edges"]}
        new_keys = {edge_key(e) for e in new_taxonomy["edges"]}
        for e in [e for e in old_taxonomy["edges"] if edge_key(e) not in new_keys]:
            old_ancestors.update((e["parent_id"], e["child_id"]))
            old_ancestors.update(old_taxonomy_ancestors.get(e["parent_id"], set()))
        for e in [e for e in new_taxonomy["edges"] if edge_key(e) not in old_keys]:
            old_ancestors.update((e["parent_id"], e["child_id"]))
            old_ancestors.update(self.ancestors(e["parent_id"]))
        if taxonomy_changed:
            for label in changed_labels:
                p = self._taxonomy_lookup.get((label["view"], label["kind"], label["label"].casefold()), view_path(label["view"], label["kind"], label["label"]))
                old_ancestors.add(p); old_ancestors.update(self.ancestors(p))
        touched = old_ancestors | (set().union(*(self.ancestors(p) for p in affected)) if affected else set())
        touched |= {p for p in set(old_nodes) | set(self.nodes) if old_nodes.get(p) != self.nodes.get(p)}
        # Contributor edge changes can affect ancestors of virtual parents, even if the
        # contributor is not itself the terminal child (e.g. Scenario -> Purpose).
        for p in affected:
            for e in self.contributions.get(p, {}).get("edges", []):
                touched.add(e["parent_id"])
                touched.update(self.ancestors(e["parent_id"]))
        eligible = {p for p, n in self.nodes.items() if self.children[p] or n["virtual"] and n["kind"] != "element"}
        eligible.update(p for p in self._taxonomy_lookup.values() if p)
        existing_nodes = {a["node_ref"] for a in self.aggregate_pages.values()}
        materialization_hash = fingerprint([self.config["aggregate_materialization_version"], self.config["aggregate_index_version"]])
        if materialization_hash != getattr(self, "_materialization_hash", None):
            touched.update(eligible)
        rebuild_nodes = (touched | (eligible - existing_nodes)) & eligible
        self._materialization_hash = materialization_hash
        rebuilt = []
        for uri, page in list(self.aggregate_pages.items()):
            if page["node_ref"] not in eligible or page["node_ref"] in rebuild_nodes:
                self.aggregate_pages.pop(uri)
                self._index_aggregate(uri, None)
        for p in sorted(rebuild_nodes):
            for page in materialize_aggregate(self, p):
                uri = page["path"]
                if uri in self.aggregate_pages and self.aggregate_pages[uri]["node_ref"] != p:
                    self.build_issues.setdefault("@aggregate", []).append({"severity": "error", "code": "page_path_collision", "path": uri})
                    continue
                self.aggregate_pages[uri] = page
                self._index_aggregate(uri, page)
                rebuilt.append(uri)
        self._inference_hash, self._taxonomy_hash = inference_hash, taxonomy_hash
        self._taxonomy_labels = deepcopy(self.config.get("taxonomy_nodes", []))
        from .aggregate import AggregatePageIndex
        if not hasattr(self, "aggregate_index"):
            self.aggregate_index = AggregatePageIndex()
        self.aggregate_index.sync(self.aggregate_pages)
        self.dependencies = new_deps
        self._hashes, self._config_hash = hashes, config_hash
        self.last_update = {"changed_entities": sorted(changed), "rebuilt_entities": sorted(affected & current.keys()),
                            "rebuilt_aggregates": rebuilt, "inference_calls": classifier.calls}
        return self

    def _build_taxonomy(self, previous=None):
        self.contributions["@taxonomy"] = {"nodes": {}, "edges": []}
        paths = {}
        for label in self.config.get("taxonomy_nodes", []):
            path = self._node(label["view"], label["kind"], label["label"], "@taxonomy")
            if path is None:
                raise ValueError("ambiguous_taxonomy_node")
            paths[label["id"]] = path
            for name in [label["label"], *label.get("aliases", [])]:
                self._taxonomy_lookup[(label["view"], label["kind"], name.casefold())] = path
        for edge in self.config.get("taxonomy_edges", []):
            parent, child = paths[edge["parent"]], paths[edge["child"]]
            label = next(n for n in self.config["taxonomy_nodes"] if n["id"] == edge["parent"])
            self._record("@taxonomy", label["view"], parent, child, "CONFIRMED", edge["evidence"],
                         source_relation="taxonomy", method="explicit_taxonomy", source=edge["provenance"]["source"])
        if previous:
            old = {e["edge_id"]: e for e in previous["edges"]}
            for edge in self.contributions["@taxonomy"]["edges"]:
                before = old.get(edge["edge_id"])
                if before and {k: v for k, v in edge.items() if k != "created_at"} == {k: v for k, v in before.items() if k != "created_at"}:
                    edge["created_at"] = before["created_at"]

    def _node(self, view, kind, name, owner):
        governed = getattr(self, "_taxonomy_lookup", {}).get((view, kind, name.casefold()))
        if governed:
            return governed
        matches = sorted(set(self._name_index.get((kind, name.casefold()), [])))
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            self.build_issues.setdefault(owner, []).append({"severity": "warning", "code": "alias_collision", "name": name})
            return None
        path = view_path(view, kind, name)
        node = {"path": path, "name": name, "kind": kind, "virtual": True, "hierarchy_id": view, "facets": {kind: name}}
        self.nodes[path] = node
        self.contributions[owner]["nodes"][path] = node
        return path

    def _record(self, owner, view, parent, child, status, evidence, *, source_relation,
                method="explicit", confidence=1.0, **provenance):
        if not parent or not child or parent == child:
            return
        for endpoint in (parent, child):
            kind = self.nodes.get(endpoint, {}).get("kind")
            if view not in self.config["applicable_views"].get(kind, []):
                self.build_issues.setdefault(owner, []).append({"severity": "error", "code": "entity_placed_in_non_applicable_view", "context": endpoint, "hierarchy_id": view})
                return
        if not evidence:
            self.build_issues.setdefault(owner, []).append({"severity": "warning", "code": "missing_provenance", "context": owner, "section": source_relation})
            return
        row = HierarchyEdge(view, parent, child, status, confidence,
            {"method": method, "source_ids": sorted({e["source"]["source_id"] for e in evidence}),
             "source_relation": source_relation, **provenance}, evidence, inference_version=self.config["version"]).to_dict()
        self.contributions[owner]["edges"].append(row)

    def _build_context(self, context):
        self.contributions[context.path] = {"edges": [], "nodes": {}}
        for reference in context.references:
            if reference.status != "CONFIRMED" or reference.target_path not in self.contexts:
                continue
            if reference.relation == "uses_model" and context.context_type in MODEL_TYPES:
                # Model dependencies are lineage, not semantic containment.
                continue
            for view, direction in RELATION_VIEWS.get(reference.relation, ()):
                parent, child = (context.path, reference.target_path) if direction == "forward" else (reference.target_path, context.path)
                # part_of is meaningful only in a view with the relevant entity kinds.
                if reference.relation == "part_of" and view != ("analysis" if context.context_type in {"scenario", "analysis-purpose"} else "domain"):
                    continue
                if reference.relation in {"uses_metric", "requires_metric", "uses_dimension", "requires_dimension"} and context.context_type in MODEL_TYPES:
                    parent, child = child, parent
                self._record(context.path, view, parent, child, "CONFIRMED", [asdict(e) for e in reference.evidence],
                             source_relation=reference.relation, source_priority="explicit_entity_relations")
        self._build_tags(context)
        for view, sections in SECTION_VIEWS.items():
            if view not in self.config["applicable_views"].get(context.context_type, []):
                continue
            previous = []
            previous_proofs = []
            previous_kind = None
            for section, kind in sections:
                status = context.section_status.get(section, "EXPLICIT")
                if status not in {"EXPLICIT", "DERIVED"}:
                    continue
                labels = values(context.sections.get(section))
                proofs = [asdict(e) for e in context.evidence.get(section, [])]
                if not labels or not proofs:
                    continue
                parents = [self._node(view, kind, name, context.path) for name in labels]
                parents = [p for p in parents if p and p != context.path]
                edge_status = "CONFIRMED" if status == "EXPLICIT" else "DERIVED"
                kwargs = {} if edge_status == "CONFIRMED" else {"method": "domain_rule", "rule_id": "governed-section-projection", "input_facts": [{"context": context.path, "section": section, "value": context.sections[section]}]}
                for p in parents:
                    start, end = p, context.path
                    if view == "analysis" and VIEWS[view].index(context.context_type) < VIEWS[view].index(kind):
                        start, end = end, start
                    self._record(context.path, view, start, end, edge_status, proofs,
                                 source_relation=section, source_priority="explicit_document_mapping", **kwargs)
                    # Co-classification only creates an organization edge; never a typed fact.
                    for prev in previous:
                        if view == "analysis" and {previous_kind,kind} <= {"metric","dimension"}:
                            continue
                        supported = self._pair_supported(view, prev, p)
                        if self.config["co_classification_guard"] and len(previous) > 1 and len(parents) > 1 and not supported:
                            continue
                        self._record(context.path, view, prev, p, "DERIVED", previous_proofs + proofs,
                            source_relation="co_classification", method="domain_rule", rule_id=self.config["co_classification_guard_version"],
                            parent_cardinality=len(previous), child_cardinality=len(parents), pair_supported=supported,
                            input_facts=[{"context": context.path, "parent": prev, "child": p}], confidence=.95)
                if parents:
                    previous, previous_proofs, previous_kind = parents, proofs, kind

        if context.context_type == "physical-model" and context.section_status.get("important_fields", "EXPLICIT") in {"EXPLICIT", "DERIVED"}:
            fields = context.sections.get("important_fields", [])
            if isinstance(fields, list):
                for value in fields[:self.config.get("important_element_limit", 8)]:
                    label = values(value.get("name", value.get("field_name", value.get("field")))) if isinstance(value, dict) else values(value)
                    if not label or (isinstance(value, dict) and value.get("status", "EXPLICIT") not in {"EXPLICIT", "DERIVED"}):
                        continue
                    path = hierarchy_path("elements", "asset", context.canonical_id, label[0])
                    node = {"path": path, "name": label[0], "kind": "element", "virtual": True,
                            "hierarchy_id": "asset", "parent_context": context.path, "facets": {}}
                    self.nodes[path] = node
                    self.contributions[context.path]["nodes"][path] = node
                    self._record(context.path, "asset", context.path, path, "DERIVED",
                        [asdict(e) for e in context.evidence.get("important_fields", [])],
                        source_relation="important_fields", method="domain_rule", rule_id="important-element-projection/v1",
                        input_facts=[{"context": context.path, "section": "important_fields", "value": label[0]}])

    def _pair_supported(self, view, parent, child):
        if any(e["hierarchy_id"] == view and e["parent_id"] == parent and e["child_id"] == child
               for e in self.contributions.get("@taxonomy", {}).get("edges", [])):
            return True
        for source, target in ((parent, child), (child, parent)):
            context = self.contexts.get(source)
            for ref in context.references if context else ():
                if ref.status != "CONFIRMED" or ref.target_path != target or not ref.evidence:
                    continue
                for relation_view, direction in RELATION_VIEWS.get(ref.relation, ()):
                    a, b = (source, target) if direction == "forward" else (target, source)
                    if relation_view == view and (a, b) == (parent, child):
                        return True
        return False

    def _build_tags(self, context):
        if context.section_status.get("tags", "EXPLICIT") != "EXPLICIT":
            return
        tags = context.sections.get("tags", [])
        tags = tags if isinstance(tags, list) else [tags]
        proofs = [asdict(e) for e in context.evidence.get("tags", [])]
        for tag in tags:
            if isinstance(tag, dict) and tag.get("status", "EXPLICIT") == "EXPLICIT":
                view, kind, label = tag.get("hierarchy_id"), tag.get("kind"), tag.get("label")
                if view in VIEWS and kind in VIEWS[view] and isinstance(label,str) and label:
                    parent = self._node(view, kind, label, context.path)
                    self._record(context.path, view, parent, context.path, "CONFIRMED", proofs,
                        source_relation="tags", source_priority="model_tags")
            elif isinstance(tag, str):
                for mapping in self.config.get("tag_mappings", []):
                    if mapping["tag"] == tag:
                        parent = self._node(mapping["view"], mapping["kind"], mapping["label"], context.path)
                        self._record(context.path, mapping["view"], parent, context.path, "DERIVED", proofs,
                            source_relation="tags", method="domain_rule", rule_id=mapping["rule_id"],
                            source_priority="model_tags", input_facts=[{"context": context.path, "section": "tags", "value": tag}], confidence=.95)

    def _add_placement(self, context, view, kind, label, status, confidence, evidence, provenance):
        parent = self._node(view, kind, label, context.path)
        self._record(context.path, view, parent, context.path, status, evidence,
                     source_relation="semantic_overlay", confidence=confidence, **provenance)

    def _reindex(self):
        self.parents, self.children = defaultdict(list), defaultdict(list)
        unique = {}
        for owner, record in sorted(self.contributions.items()):
            for e in record["edges"]:
                key = e["edge_id"]
                if key not in unique:
                    unique[key] = {**deepcopy(e), "owners": []}
                row = unique[key]
                row["owners"].append(owner)
                for proof in e["evidence"]:
                    if proof not in row["evidence"]:
                        row["evidence"].append(proof)
                row["provenance"]["source_ids"] = sorted(set(row["provenance"]["source_ids"]) | set(e["provenance"]["source_ids"]))
        self.edges = sorted(unique.values(), key=lambda e: e["edge_id"])
        groups = defaultdict(list)
        for e in self.edges:
            groups[(e["hierarchy_id"], e["child_id"], self.nodes.get(e["parent_id"], {}).get("kind"))].append(e)
        self.conflicts = []
        for (view, child, kind), edges in groups.items():
            def priority(edge):
                return (edge["provenance"].get("method") == "explicit_taxonomy", STATUS_RANK.get(edge["status"], 0))
            best = max(priority(e) for e in edges)
            for e in edges:
                e["active"] = e["status"] != "CANDIDATE" and priority(e) == best
                # No candidate placement participates in strong navigation.
            if len({e["parent_id"] for e in edges}) > 1:
                self.conflicts.append({"hierarchy_id": view, "child_id": child, "kind": kind,
                    "code": "conflicting_confirmed_placement" if sum(e["status"] == "CONFIRMED" for e in edges) > 1 else "placement_conflict",
                    "edge_ids": [e["edge_id"] for e in edges], "policy": "status_precedence_preserve_audit"})
        for e in self.edges:
            self.parents[e["child_id"]].append(e)
            self.children[e["parent_id"]].append(e)

    def ancestors(self, path, view=None):
        return self._walk(path, "parents", view)

    def descendants(self, path, view=None):
        return self._walk(path, "children", view)

    def _walk(self, path, direction, view):
        result, pending = set(), [(path, view)]
        visited = set()
        while pending:
            current, selected_view = pending.pop()
            if (current, selected_view) in visited:
                continue
            visited.add((current, selected_view))
            for e in getattr(self, direction).get(current, []):
                if not e["active"] or (selected_view and e["hierarchy_id"] != selected_view):
                    continue
                other = e["parent_id"] if direction == "parents" else e["child_id"]
                if other != path:
                    result.add(other)
                pending.append((other, e["hierarchy_id"]))
        return result

    def _index_aggregate(self, path, page):
        from .page import toks
        for view, terms in self.aggregate_terms.pop(path, {}).items():
            for term in terms:
                self.branch_postings[view][term].discard(path)
        self.branch_membership.pop(path, None)
        self.branch_previews.pop(path, None)
        if page is None:
            return
        members = tuple(dict.fromkeys(([page["canonical_ref"]] if page.get("canonical_ref") else []) + page["member_refs"]))
        self.branch_membership[path] = frozenset(members)
        # Offline deterministic fallback; query never walks all member_refs.
        self.branch_previews[path] = members[:1000]
        self.aggregate_terms[path] = {}
        for view, content in page["views"].items():
            terms = set(toks(content["L0"]))
            for label in self.config.get("taxonomy", []):
                if label["view"] == view and label["label"] == page["name"]:
                    terms.update(toks(" ".join(label.get("aliases", []))))
            self.aggregate_terms[path][view] = terms
            for term in terms:
                self.branch_postings[view][term].add(path)

    def recall_branches(self, terms, view):
        return set().union(*(self.branch_postings[view].get(t, set()) for t in terms)) if terms else set()

    def classification(self, path):
        applicable = self.config["applicable_views"].get(self.nodes.get(path, {}).get("kind"), [])
        views = {v: [e for e in self.parents.get(path, []) if e["hierarchy_id"] == v and e["active"]
                      and e["status"] in {"CONFIRMED", "DERIVED"}] for v in applicable}
        placed = [v for v, es in views.items() if es]
        return {"status": "classified" if applicable and len(placed) == len(applicable) else "partially_classified" if placed else "unclassified",
                "applicable_views": list(applicable),
                "confirmed_views": [v for v, es in views.items() if any(e["status"] == "CONFIRMED" for e in es)],
                "derived_views": [v for v, es in views.items() if any(e["status"] == "DERIVED" for e in es)],
                "candidate_views": [v for v in applicable if any(e["status"] == "CANDIDATE" and e["hierarchy_id"] == v for e in self.parents.get(path, []))],
                "missing_views": [v for v in applicable if not views[v]],
                "views": {v: [e["edge_id"] for e in es] for v, es in views.items()}}

    def resolve_path(self, path):
        if path.startswith("hierarchy://models/"):
            parts = [unquote(p) for p in path.removeprefix("hierarchy://models/").split("/")]
            if len(parts) == 1:
                return view_path("asset", "layer", parts[0])
            if len(parts) == 2:
                return view_path("domain", "topic-domain", parts[1])
            if len(parts) == 3:
                return view_path("domain", "topic", parts[2])
        return path

    def has(self, path):
        return self.resolve_path(path) in self.nodes or path in self.aggregate_pages

    def describe(self, path, view=None):
        path = self.resolve_path(path)
        if path in self.aggregate_pages:
            page = self.aggregate_pages[path]
            view = view or page["hierarchy_view"]
            path = page["node_ref"]
        if path not in self.nodes:
            return {}
        def visible(edges):
            return [e for e in edges if not view or e["hierarchy_id"] == view]
        parents, children = visible(self.parents[path]), visible(self.children[path])
        # Breadcrumb is a compatibility preview; all placements are in views/parents.
        breadcrumbs = {v: self._breadcrumb(path, v) for v in VIEWS}
        preview = next((b for b in breadcrumbs.values() if len(b) > 1), [dict(self.nodes[path])])
        return {"node": dict(self.nodes[path]), "breadcrumb": breadcrumbs.get(view, preview), "breadcrumbs": breadcrumbs,
                "parents": [{**e, "node": dict(self.nodes.get(e["parent_id"], {}))} for e in parents],
                "children": [{**e, "node": dict(self.nodes.get(e["child_id"], {}))} for e in children],
                "classification": self.classification(path),
                "conflicts": [c for c in self.conflicts if c["child_id"] == path]}

    def navigation(self, path, limit=20):
        """L1 organization summary; full provenance is an explicit focused L2 read."""
        result = self.describe(path)
        if not result:
            return result
        result["edge_counts"] = {side:len(result[side]) for side in ("parents", "children")}
        result["truncated"] = any(count > limit for count in result["edge_counts"].values())
        for side in ("parents", "children"):
            result[side] = [{
                **{k:e[k] for k in ("edge_id", "hierarchy_id", "parent_id", "child_id", "status", "confidence", "active")},
                "node": {k:e["node"][k] for k in ("path", "name", "kind", "virtual")},
                "provenance": {k:v for k,v in e["provenance"].items() if k in {"method", "rule_id", "source_ids"}},
                "evidence_count": len(e["evidence"]),
            } for e in result[side][:limit]]
        return result

    def _breadcrumb(self, path, view):
        trail, seen, current = [], set(), path
        while current in self.nodes and current not in seen:
            seen.add(current)
            trail.append(dict(self.nodes[current]))
            incoming = [e for e in self.parents[current] if e["active"] and e["hierarchy_id"] == view]
            if not incoming:
                break
            current = sorted(incoming, key=lambda e: (not self.nodes[e["parent_id"]]["virtual"], e["parent_id"]))[0]["parent_id"]
        return list(reversed(trail))

    def validate(self):
        issues = [i for rows in self.build_issues.values() for i in rows]
        from ..hierarchy_config import validate_hierarchy_config
        try:
            validate_hierarchy_config(self.config)
        except ValueError as exc:
            issues.append({"severity": "error", "code": str(exc)})
        if getattr(self, "_config_hash", None) != fingerprint(self.config):
            issues.append({"severity": "error", "code": "organization_config_stale"})
        seen = set()
        known_evidence = {json.dumps(asdict(e),sort_keys=True) for c in self.contexts.values()
                          for rows in [*c.evidence.values(), *[r.evidence for r in c.references]] for e in rows}
        for edge in self.config.get("taxonomy_edges", []):
            known_evidence.update(json.dumps(e, sort_keys=True) for e in edge["evidence"])
        for e in self.edges:
            provenance = e.get("provenance", {})
            if (self.config["co_classification_guard"] and e["status"] == "DERIVED" and
                provenance.get("source_relation") == "co_classification" and
                provenance.get("parent_cardinality", 2) > 1 and provenance.get("child_cardinality", 2) > 1 and
                not self._pair_supported(e["hierarchy_id"], e["parent_id"], e["child_id"])):
                issues.append({"severity": "error", "code": "ambiguous_derived_edge", "edge_id": e["edge_id"]})
            for endpoint in (e["parent_id"], e["child_id"]):
                if endpoint in self.nodes and e["hierarchy_id"] not in self.config["applicable_views"].get(self.nodes[endpoint]["kind"], []):
                    issues.append({"severity": "error", "code": "entity_placed_in_non_applicable_view", "context": endpoint})
            if e["status"] == "CANDIDATE" and e.get("active"):
                issues.append({"severity": "error", "code": "candidate_as_classified", "edge_id": e["edge_id"]})
            if any(json.dumps(proof,sort_keys=True) not in known_evidence for proof in e.get("evidence", [])):
                issues.append({"severity": "error", "code": "evidence_not_found", "edge_id": e.get("edge_id")})
            for code in edge_errors(e):
                issues.append({"severity": "error", "code": code, "edge_id": e.get("edge_id")})
            if e["edge_id"] in seen:
                issues.append({"severity": "error", "code": "duplicate_edge"})
            seen.add(e["edge_id"])
            if any(p not in self.nodes for p in (e["parent_id"], e["child_id"])):
                issues.append({"severity": "error", "code": "broken_parent_reference", "edge_id": e["edge_id"]})
        # Cycle detection includes candidates, which may never bypass the gate.
        for view in VIEWS:
            indegree = {p: 0 for p in self.nodes}
            outgoing = defaultdict(set)
            for e in self.edges:
                if e["hierarchy_id"] == view and e["parent_id"] in indegree and e["child_id"] in indegree and e["child_id"] not in outgoing[e["parent_id"]]:
                    outgoing[e["parent_id"]].add(e["child_id"])
                    indegree[e["child_id"]] += 1
            ready = [p for p, n in indegree.items() if n == 0]
            visited = 0
            while ready:
                p = ready.pop(); visited += 1
                for child in outgoing[p]:
                    indegree[child] -= 1
                    if indegree[child] == 0:
                        ready.append(child)
            if visited != len(indegree):
                issues.append({"severity": "error", "code": "hierarchy_cycle", "hierarchy_id": view})
        exclusive = {(slot["view"],slot["kind"]) for slot in self.config.get("exclusive_slots", [])}
        issues.extend({"severity": "error" if c["code"]=="conflicting_confirmed_placement" and (c["hierarchy_id"],c["kind"]) in exclusive else "warning", **c} for c in self.conflicts)
        for p, page in self.aggregate_pages.items():
            members = frozenset(page["member_refs"]) | ({page["canonical_ref"]} if page.get("canonical_ref") else set())
            if self.branch_membership.get(p) != members or self.branch_previews.get(p) != tuple(dict.fromkeys(([page["canonical_ref"]] if page.get("canonical_ref") else []) + page["member_refs"]))[:1000]:
                issues.append({"severity": "error", "code": "branch_member_index_stale", "path": p})
            if p in self.contexts:
                issues.append({"severity": "error", "code": "page_path_collision", "path": p})
            if p != page["path"] or not p.startswith("data://views/" + page["hierarchy_view"] + "/") or set(page["views"]) != {page["hierarchy_view"]}:
                issues.append({"severity": "error", "code": "view_uri_mismatch", "path": p})
            for view, content in page["views"].items():
                expected = sorted(self.descendants(page["node_ref"], view) & self.contexts.keys())
                if content["L2"]["members"] != expected:
                    issues.append({"severity": "error", "code": "aggregate_member_mismatch", "path": p})
        if hasattr(self, "aggregate_index") and not self.aggregate_index.is_current(self.aggregate_pages):
            issues.append({"severity": "error", "code": "aggregate_index_stale"})
        return issues

    def to_dict(self):
        return {"version": VERSION, "config": self.config, "contributions": self.contributions,
                "inference_audit": self.inference_audit, "build_issues": self.build_issues,
                "aggregate_pages": self.aggregate_pages, "dependencies": self.dependencies,
                "hashes": self._hashes, "config_hash": self._config_hash, "history": self.history,
                "inference_hash": self._inference_hash, "taxonomy_hash": self._taxonomy_hash,
                "materialization_hash": self._materialization_hash,
                "taxonomy_labels": self._taxonomy_labels,
                "aggregate_index_manifest": self.aggregate_index.manifest}

    @classmethod
    def from_dict(cls, value, contexts):
        if value.get("version") != VERSION:
            raise ValueError("organization snapshot version mismatch; rebuild from canonical sources for V1.1")
        if value["config_hash"] != fingerprint(value["config"]):
            raise ValueError("organization config fingerprint mismatch")
        index = cls(value["config"])
        if index.config != value["config"]:
            raise ValueError("retrieval_policy_version_mismatch; rebuild snapshot")
        index.contexts = {c.path: c for c in contexts if c.identity_status not in {"INFERRED", "CANDIDATE"}}
        index.contributions = value["contributions"]
        index.nodes = {p: {"path": p, "name": c.name, "kind": c.context_type, "virtual": False, "facets": {k:c.sections[k] for k in ("topic_domain", "topic", "classification.layer") if k in c.sections}}
                       for p, c in index.contexts.items()}
        for record in index.contributions.values():
            index.nodes.update(record["nodes"])
        index._reindex()
        index.aggregate_pages = value["aggregate_pages"]
        from .page import toks
        for p, a in index.aggregate_pages.items():
            index._index_aggregate(p, a)
        index.inference_audit = value["inference_audit"]
        index.history = value.get("history", [])
        index.build_issues = value.get("build_issues", {})
        index.dependencies = value["dependencies"]
        index._hashes, index._config_hash = value["hashes"], value["config_hash"]
        index._inference_hash, index._taxonomy_hash = value["inference_hash"], value["taxonomy_hash"]
        index._taxonomy_labels = value["taxonomy_labels"]
        index._materialization_hash = value["materialization_hash"]
        from .aggregate import AggregatePageIndex
        index.aggregate_index = AggregatePageIndex()
        index.aggregate_index.sync(index.aggregate_pages)
        if index.aggregate_index.manifest != value["aggregate_index_manifest"]:
            raise ValueError("aggregate_index_stale")
        return index

    @property
    def edge_count(self):
        return len(self.edges)
