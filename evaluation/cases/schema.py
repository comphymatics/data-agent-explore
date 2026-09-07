"""Scorer-side Pilot validation; none of this metadata reaches adapters."""
from collections import Counter
from evaluation.benchmark.result_contract import CATEGORIES, ENTITY_TYPES, RELATION_TYPES

PILOT_TARGETS = dict(zip(CATEGORIES, (10, 12, 8, 8, 10, 8, 4)))


def validate_cases(rows, registry, documents, smoke=False):
    if not isinstance(rows, list) or not rows:
        raise ValueError("empty case set")
    ids = set()
    for row in rows:
        if not isinstance(row.get("case_id"), str) or not row["case_id"].strip() or row["case_id"] in ids:
            raise ValueError("cases require unique nonempty IDs")
        ids.add(row["case_id"])
        if not isinstance(row.get("query"), str) or not row["query"].strip():
            raise ValueError("nonempty query required")
        if row.get("category") not in CATEGORIES:
            raise ValueError("unsupported Pilot category")
        if row.get("review_status") not in ({"APPROVED", "FIXTURE"} if smoke else {"APPROVED"}):
            raise ValueError("formal cases require human-approved Gold")
        if row.get("difficulty") not in {"easy", "medium", "hard"}:
            raise ValueError("difficulty must be easy, medium or hard")
        if not isinstance(row.get("tags"), list) or any(not isinstance(t, str) for t in row["tags"]):
            raise ValueError("tags must be a string list")
        span = row.get("source_span")
        sources = row.get("source_documents", [])
        if not isinstance(sources, list) or any(not isinstance(s, str) for s in sources):
            raise ValueError("source_documents must be a list")
        sources = set(sources)
        if span not in {"single_document", "cross_document"} or not sources or not sources <= documents:
            raise ValueError("invalid source-span declaration")
        if span == "single_document" and len(sources) != 1:
            raise ValueError("single-document cases require exactly one source")
        if span == "cross_document" and (len(sources) < 2 or not row.get("cross_document_rationale")):
            raise ValueError("cross-document cases require multiple sources and a necessity rationale")
        if not isinstance(row.get("expected_empty"), bool):
            raise ValueError("expected_empty must be explicit boolean")
        gold = row.get("gold")
        if not isinstance(gold, dict) or set(gold) - set(ENTITY_TYPES):
            raise ValueError("unsupported Gold entity type")
        required = set()
        for typ, values in gold.items():
            if not isinstance(values, list) or any(not isinstance(c, str) for c in values) or len(values) != len(set(values)):
                raise ValueError("Gold values must be unique ID lists")
            for cid in values:
                if cid not in registry.entities or registry.entities[cid]["type"] != typ:
                    raise ValueError("Gold ID missing or type mismatch")
            required.update(values)
        for key in ("optional", "forbidden"):
            if not isinstance(row.get(key, []), list) or any(not isinstance(c, str) for c in row.get(key, [])):
                raise ValueError("optional/forbidden must be ID lists")
        optional = set(row.get("optional", [])); forbidden = set(row.get("forbidden", []))
        if not (optional | forbidden) <= set(registry.entities):
            raise ValueError("optional/forbidden IDs must belong to the scorer registry")
        if required & optional or (required | optional) & forbidden:
            raise ValueError("required/optional/forbidden sets must be disjoint")
        if row["expected_empty"]:
            if required or optional or row.get("relations") or not row.get("empty_rationale"):
                raise ValueError("negative cases require empty Gold/optional/relations and reviewed material-scoped rationale")
        elif not required or row["category"] == "negative":
            raise ValueError("positive cases require Gold; negative category requires expected_empty")
        relations = row.get("relations")
        if relations is not None:
            if not isinstance(relations, list): raise ValueError("relations must be a list or null (unannotated)")
            seen = set()
            for edge in relations:
                if (not isinstance(edge, dict) or set(edge) != {"source", "relation", "target"}
                        or edge["relation"] not in RELATION_TYPES
                        or edge["source"] not in required | optional or edge["target"] not in required | optional):
                    raise ValueError("Gold relation requires supported type and required/optional entity endpoints")
                key = (edge["source"], edge["relation"], edge["target"])
                if key in seen: raise ValueError("duplicate Gold relation")
                seen.add(key)
    return rows


def distribution(rows):
    categories = Counter(r["category"] for r in rows)
    spans = Counter(r["source_span"] for r in rows)
    ratio = spans["cross_document"] / len(rows) if rows else 0
    warnings = [f"{cat}: {categories[cat]}/{target} recommended cases" for cat, target in PILOT_TARGETS.items() if categories[cat] < target]
    if ratio < .6: warnings.append(f"cross-document fraction {ratio:.1%} is below recommended 60%")
    return {"total": len(rows), "categories": {k: categories[k] for k in CATEGORIES},
            "source_spans": dict(spans), "difficulties": dict(Counter(r["difficulty"] for r in rows)),
            "cross_document_fraction": ratio, "recommended_targets": PILOT_TARGETS, "warnings": warnings}
