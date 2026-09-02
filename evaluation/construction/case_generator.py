from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict, deque
from pathlib import Path
from typing import Any, Iterable

from evaluation.benchmark.io import read_json, read_jsonl, write_json, write_jsonl


GOLD_STATUSES = {"EXPLICIT", "DERIVED"}
LAYER_MAP = {
    "scenario": "scenario",
    "metric": "metric",
    "business_object": "business_object",
    "logical_model": "logical_model",
    "physical_model": "physical_model",
    "table": "table",
    "field": "field",
    "dimension": "dimension",
    "grain": "grain",
    "processing_rule": "processing_logic",
    "environment_asset": "environment_asset",
    "target_model": "physical_model",
}
SCHEMA_TERMS = {
    "field",
    "column",
    "grain",
    "granularity",
    "key",
    "dimension",
    "data_type",
    "partition",
    "storage",
    "schema",
}
PROCESS_TERMS = {
    "formula",
    "processing",
    "source",
    "upstream",
    "lineage",
    "join",
    "filter",
    "aggregate",
    "deduplicate",
    "mapping",
}
GAP_TERMS = {"missing", "unavailable", "not_available", "conflict", "inconsistent"}
SUBTYPES = {
    "single_layer",
    "adjacent_mapping",
    "multi_layer",
    "environment_gap_conflict",
    "schema_context",
    "processing_context",
    "full_design_context",
    "reuse_and_change",
    "insufficient_context",
}


def _is_entity(value: Any) -> bool:
    return isinstance(value, dict) and {"entity_id", "entity_type", "name"} <= set(value)


def _eligible(record: dict[str, Any]) -> bool:
    return (
        record.get("review_status") == "APPROVED"
        and record.get("assertion_status") in GOLD_STATUSES
    )


def _eligible_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id = {record["evidence_id"]: record for record in records}
    memo: dict[str, bool] = {}

    def visit(evidence_id: str, visiting: set[str]) -> bool:
        if evidence_id in memo:
            return memo[evidence_id]
        if evidence_id in visiting:
            memo[evidence_id] = False
            return False
        record = by_id.get(evidence_id)
        if not record or not _eligible(record):
            memo[evidence_id] = False
            return False
        if record.get("assertion_status") == "EXPLICIT":
            memo[evidence_id] = True
            return True
        parents = record.get("derived_from", [])
        valid = bool(parents) and all(visit(parent, visiting | {evidence_id}) for parent in parents)
        memo[evidence_id] = valid
        return valid

    return [record for record in records if visit(record["evidence_id"], set())]


def _slug_hash(*parts: str, length: int = 12) -> str:
    raw = "\x1f".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]


def _case_id(family: str, subtype: str, required: Iterable[str]) -> str:
    digest = _slug_hash(family, subtype, *sorted(required))
    family_short = "research" if family == "requirement_research" else "design"
    return f"case-auto-{family_short}-{subtype.replace('_', '-')}-{digest}"


def _difficulty(required_count: int, layer_count: int) -> tuple[str, int]:
    if required_count <= 1 and layer_count <= 2:
        return "S", 2048
    if required_count <= 3 and layer_count <= 4:
        return "M", 4096
    return "L", 8192


def _entity_layers(records: Iterable[dict[str, Any]]) -> list[str]:
    layers: set[str] = set()
    for record in records:
        for value in (record.get("subject"), record.get("object")):
            if _is_entity(value):
                layer = LAYER_MAP.get(value["entity_type"])
                if layer:
                    layers.add(layer)
        predicate = str(record.get("predicate", "")).lower()
        if any(term in predicate for term in PROCESS_TERMS):
            layers.add("processing_logic")
        if "grain" in predicate or "granularity" in predicate:
            layers.add("grain")
    return sorted(layers)


def _relation_query(record: dict[str, Any]) -> str:
    subject = record["subject"]["name"]
    obj = record.get("object", {})
    object_name = obj.get("name") if _is_entity(obj) else str(obj.get("value", ""))
    predicate = record["predicate"]
    templates = {
        "uses_metric": f"场景“{subject}”涉及哪些指标？请给出可追溯依据。",
        "provided_by": f"“{subject}”由哪个现有模型提供？请定位到权威证据。",
        "materialized_as": f"“{subject}”最终物化到哪张表？",
        "has_field": f"“{subject}”包含哪个相关字段？字段用途是什么？",
        "has_grain": f"“{subject}”的数据粒度是什么？",
        "implements_metric": f"“{subject}”实现了哪个指标？",
        "implements_dimension": f"“{subject}”实现了哪个维度？",
        "implements_logical_model": f"“{subject}”对应哪个逻辑模型？",
        "upstream_model": f"“{subject}”的上游模型是什么？",
    }
    return templates.get(
        predicate,
        f"请调研“{subject}”与“{object_name}”之间的“{predicate}”关系，并给出证据。",
    )


def _case(
    family: str,
    subtype: str,
    query: str,
    required_records: list[dict[str, Any]],
    *,
    allowed: list[str] | None = None,
    forbidden: list[str] | None = None,
    environment_scope: str = "global",
    expected_missing: list[str] | None = None,
    expected_conflicts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    required = list(dict.fromkeys(record["evidence_id"] for record in required_records))
    layers = _entity_layers(required_records) or ["scenario"]
    difficulty, budget = _difficulty(len(required), len(layers))
    case_id = _case_id(family, subtype, required)
    return {
        "case_id": case_id,
        "scenario_family": family,
        "subtype": subtype,
        "query": query,
        "query_variants": [f"换一种业务表达：{query}"],
        "difficulty": difficulty,
        "environment_scope": environment_scope,
        "context_token_budget": budget,
        "required_layers": layers,
        "required_evidence": required,
        "allowed_relevant_evidence": list(allowed or []),
        "forbidden_evidence": list(forbidden or []),
        "expected_missing": list(expected_missing or []),
        "expected_conflicts": list(expected_conflicts or []),
        "negative": False,
        "review_status": "DRAFT",
        "reviewer_ids": [],
        "notes": "AUTO_GENERATED_CANDIDATE: query wording and Gold sets require review",
    }


def _neighbors(records: list[dict[str, Any]]) -> tuple[dict[str, list[tuple[str, dict[str, Any]]]], dict[str, dict[str, Any]]]:
    adjacency: dict[str, list[tuple[str, dict[str, Any]]]] = defaultdict(list)
    entities: dict[str, dict[str, Any]] = {}
    for record in records:
        subject = record.get("subject")
        obj = record.get("object")
        if not _is_entity(subject):
            continue
        entities[subject["entity_id"]] = subject
        if not _is_entity(obj):
            continue
        entities[obj["entity_id"]] = obj
        adjacency[subject["entity_id"]].append((obj["entity_id"], record))
        adjacency[obj["entity_id"]].append((subject["entity_id"], record))
    for node in adjacency:
        adjacency[node].sort(key=lambda item: (item[1]["evidence_id"], item[0]))
    return adjacency, entities


def _incident_ids(
    node_ids: set[str],
    records: list[dict[str, Any]],
    *,
    gold_ids: set[str],
    eligible: bool,
    excluded: set[str],
    limit: int = 4,
) -> list[str]:
    values: list[str] = []
    for record in records:
        if (record["evidence_id"] in gold_ids) != eligible or record["evidence_id"] in excluded:
            continue
        if not eligible and not (
            record.get("assertion_status") in {"INFERRED", "CANDIDATE"}
            or record.get("review_status") == "REJECTED"
        ):
            continue
        subject_id = record.get("subject", {}).get("entity_id")
        object_id = record.get("object", {}).get("entity_id") if _is_entity(record.get("object")) else None
        if subject_id in node_ids or object_id in node_ids:
            values.append(record["evidence_id"])
    return sorted(dict.fromkeys(values))[:limit]


def _path_candidates(
    approved: list[dict[str, Any]],
    all_records: list[dict[str, Any]],
    gold_ids: set[str],
    max_paths: int,
) -> list[dict[str, Any]]:
    adjacency, entities = _neighbors(approved)
    candidates: list[dict[str, Any]] = []
    seen_edges: set[tuple[str, ...]] = set()
    expansions = 0
    expansion_limit = max_paths * 100
    preferred_starts = {
        "scenario",
        "metric",
        "business_object",
        "logical_model",
        "physical_model",
    }
    for start in sorted(adjacency):
        if entities.get(start, {}).get("entity_type") not in preferred_starts:
            continue
        stack = [(start, [start], [])]
        while stack and len(candidates) < max_paths and expansions < expansion_limit:
            node, nodes, edges = stack.pop()
            expansions += 1
            if 3 <= len(edges) <= 6:
                signature = tuple(sorted(edge["evidence_id"] for edge in edges))
                if signature not in seen_edges:
                    seen_edges.add(signature)
                    required_set = set(signature)
                    node_set = set(nodes)
                    allowed = _incident_ids(
                        node_set, all_records, gold_ids=gold_ids, eligible=True, excluded=required_set
                    )
                    forbidden = _incident_ids(
                        node_set, all_records, gold_ids=gold_ids, eligible=False, excluded=set()
                    )
                    end = entities[nodes[-1]]["name"]
                    begin = entities[nodes[0]]["name"]
                    candidates.append(
                        _case(
                            "requirement_research",
                            "multi_layer",
                            f"请从“{begin}”出发，调研到“{end}”的完整企业数据映射链路，并逐层给出依据。",
                            edges,
                            allowed=allowed,
                            forbidden=forbidden,
                        )
                    )
            if len(edges) == 6:
                continue
            for neighbor, record in reversed(adjacency[node]):
                if neighbor not in nodes:
                    stack.append((neighbor, nodes + [neighbor], edges + [record]))
        if len(candidates) >= max_paths or expansions >= expansion_limit:
            break
    return candidates


def _nearby_records(
    anchor: str,
    approved: list[dict[str, Any]],
    adjacency: dict[str, list[tuple[str, dict[str, Any]]]],
    depth: int = 2,
) -> list[dict[str, Any]]:
    nodes = {anchor}
    queue = deque([(anchor, 0)])
    while queue:
        node, current_depth = queue.popleft()
        if current_depth >= depth:
            continue
        for neighbor, _ in adjacency.get(node, []):
            if neighbor not in nodes:
                nodes.add(neighbor)
                queue.append((neighbor, current_depth + 1))
    result = []
    for record in approved:
        subject_id = record.get("subject", {}).get("entity_id")
        object_id = record.get("object", {}).get("entity_id") if _is_entity(record.get("object")) else None
        if subject_id in nodes or object_id in nodes:
            result.append(record)
    return sorted(result, key=lambda item: item["evidence_id"])


def _matching(records: list[dict[str, Any]], terms: set[str]) -> list[dict[str, Any]]:
    return [
        record
        for record in records
        if any(term in str(record.get("predicate", "")).lower() for term in terms)
    ]


def _design_candidates(
    approved: list[dict[str, Any]],
    all_records: list[dict[str, Any]],
    gold_ids: set[str],
) -> list[dict[str, Any]]:
    adjacency, entities = _neighbors(approved)
    anchors = sorted(
        entity_id
        for entity_id, entity in entities.items()
        if entity["entity_type"] in {"physical_model", "table", "target_model"}
    )
    result: list[dict[str, Any]] = []
    for anchor in anchors:
        nearby = _nearby_records(anchor, approved, adjacency)
        schema_records = _matching(nearby, SCHEMA_TERMS)[:8]
        processing_records = _matching(nearby, PROCESS_TERMS)[:8]
        node_ids = {anchor}
        forbidden = _incident_ids(
            node_ids, all_records, gold_ids=gold_ids, eligible=False, excluded=set()
        )
        name = entities[anchor]["name"]
        if schema_records:
            result.append(
                _case(
                    "model_design_preparation",
                    "schema_context",
                    f"为复用“{name}”设计目标模型，请准备粒度、键、维度、度量和字段定义所需上下文。",
                    schema_records,
                    forbidden=forbidden,
                )
            )
        if processing_records:
            result.append(
                _case(
                    "model_design_preparation",
                    "processing_context",
                    f"为复用“{name}”设计目标模型，请准备来源、映射、公式、Join、过滤和聚合逻辑所需上下文。",
                    processing_records,
                    forbidden=forbidden,
                )
            )
        combined = list({record["evidence_id"]: record for record in schema_records + processing_records}.values())
        if schema_records and processing_records and len(combined) >= 4:
            result.append(
                _case(
                    "model_design_preparation",
                    "full_design_context",
                    f"为基于“{name}”建设新目标模型，准备完整 Schema 与加工逻辑上下文，并指出仍缺少的决策。",
                    combined[:12],
                    forbidden=forbidden,
                )
            )
    return result


def _explicit_gap_candidates(approved: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for record in approved:
        predicate = str(record.get("predicate", "")).lower()
        if not any(term in predicate for term in GAP_TERMS):
            continue
        is_conflict = "conflict" in predicate or "inconsistent" in predicate
        expected_missing = [] if is_conflict else [record["statement"]]
        result.append(
            _case(
                "requirement_research",
                "environment_gap_conflict",
                f"请核实“{record['subject']['name']}”在当前环境中的可用性、缺失项或冲突，并给出证据。",
                [record],
                environment_scope="current_environment",
                expected_missing=expected_missing,
            )
        )
    return result


def _single_and_adjacent(
    approved: list[dict[str, Any]],
    all_records: list[dict[str, Any]],
    gold_ids: set[str],
) -> list[dict[str, Any]]:
    result = []
    for record in approved:
        subject_id = record["subject"]["entity_id"]
        object_id = record.get("object", {}).get("entity_id") if _is_entity(record.get("object")) else None
        node_ids = {subject_id} | ({object_id} if object_id else set())
        forbidden = _incident_ids(
            node_ids, all_records, gold_ids=gold_ids, eligible=False, excluded=set()
        )
        if object_id:
            result.append(
                _case(
                    "requirement_research",
                    "adjacent_mapping",
                    _relation_query(record),
                    [record],
                    forbidden=forbidden,
                )
            )
        else:
            result.append(
                _case(
                    "requirement_research",
                    "single_layer",
                    _relation_query(record),
                    [record],
                    forbidden=forbidden,
                )
            )
    return result


def _blueprint(case: dict[str, Any], evidence_by_id: dict[str, dict[str, Any]]) -> dict[str, Any]:
    required = case["required_evidence"]
    return {
        "blueprint_id": "bp-" + case["case_id"].removeprefix("case-auto-"),
        "generation_version": "case-constructor/v1",
        "automation_status": "CANDIDATE",
        "candidate_case": case,
        "proposed_required_evidence": required,
        "evidence_preview": [
            {
                "evidence_id": evidence_id,
                "statement": evidence_by_id[evidence_id]["statement"],
                "source_id": evidence_by_id[evidence_id]["source"]["source_id"],
            }
            for evidence_id in required
        ],
        "oracle_required": case["scenario_family"] == "model_design_preparation",
        "review_checks": [
            "query_is_realistic_and_does_not_leak_entity_ids",
            "required_evidence_is_minimal_and_sufficient",
            "allowed_and_forbidden_sets_are_complete",
            "missing_and_conflicts_are_evidence_backed",
            "two_reviewers_approve_before_promotion",
        ],
    }


def generate_case_candidates(
    evidence_path: Path,
    quotas_path: Path,
    output_dir: Path,
    *,
    max_paths: int = 1000,
) -> dict[str, Any]:
    if max_paths < 1:
        raise ValueError("max_paths must be at least 1")
    records = read_jsonl(evidence_path)
    quotas_config = read_json(quotas_path)
    quotas = quotas_config.get("quotas", {})
    if not isinstance(quotas, dict):
        raise ValueError("quotas must be a JSON object")
    unknown_subtypes = sorted(set(quotas) - SUBTYPES)
    if unknown_subtypes:
        raise ValueError(f"unknown quota subtypes: {', '.join(unknown_subtypes)}")
    if any(not isinstance(value, int) or value < 0 for value in quotas.values()):
        raise ValueError("all quotas must be non-negative integers")
    approved = _eligible_records(records)
    if not approved:
        raise ValueError("no APPROVED EXPLICIT/DERIVED Evidence is available for Gold construction")
    evidence_by_id = {record["evidence_id"]: record for record in records}
    gold_ids = {record["evidence_id"] for record in approved}

    candidates = _single_and_adjacent(approved, records, gold_ids)
    candidates.extend(_path_candidates(approved, records, gold_ids, max_paths))
    candidates.extend(_explicit_gap_candidates(approved))
    candidates.extend(_design_candidates(approved, records, gold_ids))

    deduplicated: dict[tuple[str, str, tuple[str, ...]], dict[str, Any]] = {}
    for case in candidates:
        key = (
            case["scenario_family"],
            case["subtype"],
            tuple(sorted(case["required_evidence"])),
        )
        deduplicated.setdefault(key, case)

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for case in deduplicated.values():
        grouped[case["subtype"]].append(case)
    selected: list[dict[str, Any]] = []
    deficits: dict[str, int] = {}
    for subtype, requested in quotas.items():
        available = sorted(
            grouped.get(subtype, []),
            key=lambda case: (
                -len(case["required_layers"]),
                -len(case["required_evidence"]),
                case["case_id"],
            ),
        )
        count = int(requested)
        selected.extend(available[:count])
        if len(available) < count:
            deficits[subtype] = count - len(available)

    selected.sort(key=lambda case: (case["scenario_family"], case["subtype"], case["case_id"]))
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError(f"output directory must be empty: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(output_dir / "candidate-cases.jsonl", selected)
    write_jsonl(
        output_dir / "case-blueprints.jsonl",
        [_blueprint(case, evidence_by_id) for case in selected],
    )
    subtype_counts = Counter(case["subtype"] for case in selected)
    family_counts = Counter(case["scenario_family"] for case in selected)
    report = {
        "format": "enterprise-context-case-construction-report/v1",
        "input_evidence": len(records),
        "eligible_gold_evidence": len(approved),
        "candidate_pool": len(deduplicated),
        "selected_candidates": len(selected),
        "counts_by_family": dict(sorted(family_counts.items())),
        "counts_by_subtype": dict(sorted(subtype_counts.items())),
        "requested_quotas": quotas,
        "quota_deficits": deficits,
        "promotion_blockers": [
            "all generated cases remain DRAFT until two-reviewer approval",
            "model-design cases require a separately reviewed hidden design oracle",
            "environment-gap and insufficient-context cases require explicit completeness evidence",
            "query variants are seeds and require realistic business-language rewriting",
        ],
    }
    write_json(output_dir / "construction-report.json", report)
    return report
