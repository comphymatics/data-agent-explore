"""Semantic organization contracts; never canonical or backend fact edges."""
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
import json

VIEWS = {
    "analysis": ("topic", "scenario", "analysis-purpose", "metric", "dimension", "business-object", "logical-model", "physical-model"),
    "domain": ("business-category", "data-domain", "topic-domain", "topic", "business-object", "sub-object", "logical-model", "physical-model"),
    "asset": ("layer", "logical-model", "physical-model", "element"),
}
STATUS_RANK = {"CONFIRMED": 3, "DERIVED": 2, "CANDIDATE": 1}
# Ordered policy, shared by builders and inference. Lower sources cannot promote facts.
SOURCE_PRIORITY = (
    "explicit_metadata", "explicit_document_mapping", "standard_exact_mapping",
    "model_tags", "explicit_entity_relations", "grain_dimension_metric",
    "important_fields", "neighbor_context", "dense_similarity", "llm_inference",
)
VERSION = "semantic-hierarchy/v1.1"
MATERIALIZATION_VERSION = "aggregate-view/v1.1"
ROUTING_VERSION = "intent-strategy/v1.1"
AGGREGATE_INDEX_VERSION = "aggregate-hybrid/v1.1"
APPLICABLE_VIEWS = {kind: [view for view, kinds in VIEWS.items() if kind in kinds]
                    for kind in set().union(*map(set, VIEWS.values()))}


@dataclass
class HierarchyEdge:
    hierarchy_id: str
    parent_id: str
    child_id: str
    status: str
    confidence: float
    provenance: dict
    evidence: list
    inference_version: str = VERSION
    relation: str = "organized_under"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self):
        row = asdict(self)
        # Stable identity excludes timestamps and contributor ordering.
        row["edge_id"] = "he-" + sha256(json.dumps(
            [self.hierarchy_id, self.parent_id, self.child_id, self.status,
             self.provenance.get("method"), self.provenance.get("rule_id")],
            sort_keys=True).encode()).hexdigest()[:20]
        # Compatibility names for existing offline visualization consumers.
        row.update(source=self.parent_id, target=self.child_id,
                   assertion_status="EXPLICIT" if self.status == "CONFIRMED" else self.status,
                   source_relation=self.provenance.get("source_relation", "classification"))
        return row


def edge_errors(edge):
    errors = []
    if edge.get("relation") != "organized_under":
        errors.append("invalid_hierarchy_relation")
    if not edge.get("created_at"):
        errors.append("missing_created_at")
    if edge.get("hierarchy_id") not in VIEWS:
        errors.append("invalid_hierarchy_type")
    if edge.get("status") not in STATUS_RANK:
        errors.append("invalid_hierarchy_status")
    confidence = edge.get("confidence")
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
        errors.append("confidence_out_of_range")
    provenance = edge.get("provenance") or {}
    if not provenance.get("method") or not provenance.get("source_ids") or not edge.get("evidence"):
        errors.append("missing_provenance")
    if not edge.get("inference_version"):
        errors.append("missing_inference_version")
    method = provenance.get("method")
    if edge.get("status") == "CONFIRMED" and method not in {"explicit", "explicit_taxonomy"}:
        errors.append("candidate_promoted_without_policy")
    if edge.get("status") == "DERIVED" and (method != "domain_rule" or
            not provenance.get("rule_id") or not provenance.get("input_facts")):
        errors.append("missing_rule_inputs")
    if edge.get("status") == "CANDIDATE":
        audit = provenance.get("inference", {})
        if not all(k in audit for k in ("candidate_set", "selected", "supporting_features",
                                       "supporting_context_ids", "model", "prompt_version")):
            errors.append("missing_inference_audit")
        elif audit["selected"] not in audit["candidate_set"]:
            errors.append("selection_outside_candidate_set")
        if method == "llm_inference" and not audit.get("model"):
            errors.append("missing_llm_model")
        if not audit.get("supporting_context_ids") or not audit.get("prompt_version"):
            errors.append("missing_inference_support")
    return errors

# Explicit sparse skips are allowed; reverse and unrelated kinds are not.
TAXONOMY_TRANSITIONS = {
    "domain": {"business-category": ["data-domain", "topic-domain", "topic"],
        "data-domain": ["topic-domain", "topic"], "topic-domain": ["topic"],
        "topic": ["business-object", "sub-object", "logical-model", "physical-model"],
        "business-object": ["sub-object", "logical-model", "physical-model"],
        "sub-object": ["logical-model", "physical-model"], "logical-model": ["physical-model"]},
    "analysis": {"topic": ["scenario", "analysis-purpose"], "scenario": ["analysis-purpose"],
        "analysis-purpose": ["metric", "dimension", "business-object", "logical-model", "physical-model"],
        "metric": ["logical-model", "physical-model"], "dimension": ["logical-model", "physical-model"],
        "business-object": ["logical-model", "physical-model"], "logical-model": ["physical-model"]},
    "asset": {"layer": ["logical-model", "physical-model"], "logical-model": ["physical-model"],
        "physical-model": ["element"]},
}
HARDENING_VERSION = "retrieval-hardening/v1.2"
BRANCH_RETRIEVAL_DEFAULTS = {"branch_k": 3, "entity_candidate_k": 50,
    "max_entities_examined_per_branch": 100, "bundle_k": 8}
ARBITRATION_DEFAULTS = {"enabled": True, "confidence_threshold": .8, "max_views": 2, "branch_k": 3}
