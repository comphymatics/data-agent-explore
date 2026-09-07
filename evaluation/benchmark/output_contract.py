"""Public output formatting only. This module must never import a scorer/registry."""
import json
from .result_contract import ENTITY_TYPES, RELATION_TYPES, OUTPUT_SCHEMA

TYPE_NAMES = {"scenario": "scenarios", "analysis-purpose": "purposes", "metric": "metrics",
              "dimension": "dimensions", "business-object": "business_objects",
              "logical-model": "logical_models", "physical-model": "physical_models", "field": "fields"}


def descriptor():
    return {"schema": OUTPUT_SCHEMA, "entity_types": list(ENTITY_TYPES),
            "entity_values": "document-native name strings; qualify fields as model.field",
            "relations": {"optional": True, "types": list(RELATION_TYPES),
                          "endpoint": {"type": "one of entity_types", "name": "returned entity name"}}}


def empty_output():
    return {"schema": OUTPUT_SCHEMA, **{typ: [] for typ in ENTITY_TYPES}, "relations": []}


def validate_output(value):
    if isinstance(value, str):
        value = json.loads(value)
    if not isinstance(value, dict) or value.get("schema") != OUTPUT_SCHEMA:
        raise ValueError("missing or incorrect public output schema")
    if set(value) - {"schema", "relations", *ENTITY_TYPES}:
        raise ValueError("unexpected public output fields")
    for typ in ENTITY_TYPES:
        if not isinstance(value.get(typ), list) or any(not isinstance(n, str) or not n.strip() for n in value[typ]):
            raise ValueError(f"{typ} must be an array of nonempty native names")
    if not isinstance(value.get("relations", []), list):
        raise ValueError("relations must be an array")
    for edge in value.get("relations", []):
        if not isinstance(edge, dict) or set(edge) != {"source", "relation", "target"} or edge["relation"] not in RELATION_TYPES:
            raise ValueError("invalid relation record")
        for side in ("source", "target"):
            endpoint = edge[side]
            if (not isinstance(endpoint, dict) or set(endpoint) != {"type", "name"}
                    or endpoint.get("type") not in ENTITY_TYPES
                    or endpoint.get("name") not in value[endpoint["type"]]):
                raise ValueError("relation endpoints must refer to returned typed entities")
    return value


def set_output(result, value=None):
    try:
        result.output = validate_output(result.raw_output if value is None else value)
        result.metadata["output_contract_valid"] = True
    except (ValueError, TypeError) as exc:
        result.status = "INVALID"
        result.metadata.update(output_contract_valid=False, output_contract_error=str(exc))
    return result


def bundle_output(bundle):
    """Read only assertions already delivered in the Bundle; no further retrieval."""
    output = empty_output()
    refs = {}

    def add(typ, name):
        typ = TYPE_NAMES.get(typ, typ)
        if typ in ENTITY_TYPES and isinstance(name, str) and name.strip():
            if name not in output[typ]: output[typ].append(name)
            return {"type": typ, "name": name}

    for ref in bundle.get("primary_contexts", []):
        endpoint = add(ref.get("type"), ref.get("name"))
        if endpoint: refs[ref.get("path")] = endpoint
    for section in ("analysis_context", "data_context"):
        for typ in ENTITY_TYPES:
            for ref in bundle.get(section, {}).get(typ, []):
                endpoint = add(typ, ref.get("name") if isinstance(ref, dict) else ref)
                if endpoint and isinstance(ref, dict): refs[ref.get("path")] = endpoint

    def edge(source, relation, target):
        if source and target and relation in RELATION_TYPES:
            row = {"source": source, "relation": relation, "target": target}
            if row not in output["relations"]: output["relations"].append(row)

    for path, expanded in bundle.get("focused_expansion", {}).items():
        parent = refs.get(path)
        for typ in ENTITY_TYPES:
            for value in expanded.get(typ, []):
                if isinstance(value, dict):
                    if value.get("status") in {"CANDIDATE", "INFERRED"}: continue
                    name = value.get("name") or value.get("column_name") or value.get("field_name")
                else: name = value
                if typ == "fields" and parent and isinstance(name, str): name = parent["name"] + "." + name
                child = add(typ, name)
                # Explicit typed section membership has a fixed direction; no Cartesian inference.
                if parent and typ == "metrics":
                    if parent["type"] in {"physical_models", "logical_models"}: edge(child, "supported_by", parent)
                    elif parent["type"] == "purposes": edge(parent, "requires_metric", child)
                if parent and typ == "dimensions" and parent["type"] == "purposes": edge(parent, "requires_dimension", child)
                if parent and typ == "business_objects" and parent["type"] in {"physical_models", "logical_models"}: edge(parent, "belongs_to_object", child)
        # Only already-delivered, explicitly typed supported relation records are converted.
        for direction in ("outgoing", "incoming"):
            for row in expanded.get("related", {}).get(direction, []):
                if row.get("assertion_status") not in {"EXPLICIT", "DERIVED"}: continue
                node = row.get("node", {})
                if node.get("path") and node.get("kind") in TYPE_NAMES:
                    refs[node["path"]] = add(node["kind"], node.get("name"))
                edge(refs.get(row.get("source")), row.get("relation"), refs.get(row.get("target")))
    return validate_output(output)
