from collections import defaultdict
from hashlib import sha256
import json
from .page import toks

ALIASES = {"fields": "important_fields", "counters": "metric_catalog", "formulas": "formula",
           "join_keys": "joins"}
KINDS = {"important_fields": "Field", "attributes": "Attribute", "object_attributes": "Attribute",
         "formula": "Formula", "metric_catalog": "Counter", "joins": "JoinKey"}
IDENTIFIER_KEYS = {"id", "name", "code", "field", "field_name", "attribute", "attribute_name",
                   "counter", "counter_id", "counter_name", "formula", "expression", "key",
                   "left_key", "right_key", "source_field", "target_field", "join_keys", "keys"}
SECTIONS = ("important_fields", "formula", "dimensions", "metrics", "constraints", "grain",
            "attributes", "measurement_point", "record_sources", "metric_catalog",
            "joins", "runtime_details", "primary_objects", "object_attributes")


def text_values(value):
    if isinstance(value, dict):
        return [s for v in value.values() for s in text_values(v)]
    if isinstance(value, list):
        return [s for v in value for s in text_values(v)]
    return [str(value)] if value is not None else []


def identifiers(value):
    if isinstance(value, dict):
        return list(dict.fromkeys(s for k, v in value.items() if k in IDENTIFIER_KEYS for s in text_values(v)))
    return text_values(value)


def governed(value):
    """Discard candidate assertions recursively, including nested join keys."""
    if isinstance(value, dict):
        if value.get("status", value.get("assertion_status", "EXPLICIT")) not in {"EXPLICIT", "DERIVED"}:
            return None
        return {k: cleaned for k, v in value.items() if (cleaned := governed(v)) is not None}
    if isinstance(value, list):
        return [cleaned for v in value if (cleaned := governed(v)) is not None]
    return value


class ElementIndex:
    """Searchable governed elements, always scoped to parent rich pages."""
    def __init__(self):
        self.by_page = defaultdict(dict)
        self.records = {}
        self.postings = defaultdict(set)
        self.exact = defaultdict(set)

    def add(self, page):
        for eid in [eid for eid, row in self.records.items() if row["path"] == page.path]:
            self.records.pop(eid)
            for ids in self.postings.values():
                ids.discard(eid)
            for ids in self.exact.values():
                ids.discard(eid)
        self.by_page.pop(page.path, None)
        if page.identity_status in {"INFERRED", "CANDIDATE"}:
            return
        for section in SECTIONS:
            value = governed(page.l2.get(section))
            status = page.section_status.get(section, "EXPLICIT")
            if value in (None, "", [], {}) or status not in {"EXPLICIT", "DERIVED"}:
                continue
            self.by_page[page.path][section] = value
            elements = value if isinstance(value, list) else [value]
            for offset, element in enumerate(elements):
                if isinstance(element, dict) and element.get("status", "EXPLICIT") in {"CANDIDATE", "INFERRED"}:
                    continue
                text = json.dumps(element, ensure_ascii=False, sort_keys=True)
                eid = "element-"+sha256(f"{page.path}:{section}:{offset}:{text}".encode()).hexdigest()[:20]
                row = {"element_id": eid, "path": page.path, "section": section,
                       "offset": offset, "value": element,
                       "status": element.get("status",element.get("assertion_status",status)) if isinstance(element,dict) else status,
                       "kind": KINDS.get(section, "ContextElement"), "identifiers": identifiers(element),
                       "parent_context": {"path": page.path, "name": page.name, "type": page.context_type,
                                          "content": page.l0, "knowledge_layer": "REFERENCE"}}
                self.records[eid] = row
                for key in [eid, *row["identifiers"]]:
                    self.exact[key.casefold()].add(eid)
                for token in set(toks(" ".join(text_values(element)))):
                    self.postings[token].add(eid)

    def search(self, query, paths=None, sections=None, top_k=20):
        if not isinstance(query, str) or not query.strip() or top_k < 1:
            raise ValueError("element search requires a query and positive top_k")
        terms = set(toks(query))
        allowed = {ALIASES.get(section, section) for section in (sections or []) if section != "elements"}
        # Non-element expansion requests must never accidentally search every section.
        if sections and not (allowed & set(SECTIONS)) and "elements" not in sections:
            return []
        ids = set().union(*(self.postings.get(t, set()) for t in terms)) if terms else set()
        ids |= self.exact.get(query.strip().casefold(), set())
        rows = []
        for eid in ids:
            row = self.records[eid]
            if (paths is not None and row["path"] not in paths) or (allowed and row["section"] not in allowed and "elements" not in (sections or [])):
                continue
            text = " ".join(text_values(row["value"])).casefold()
            exact = eid in self.exact.get(query.strip().casefold(), set())
            score = len(terms & set(toks(text)))/max(1, len(terms)) + 2 * exact
            rows.append({**row, "score": score, "match": "EXACT_IDENTIFIER" if exact else "TEXT"})
        return sorted(rows, key=lambda row: (-row["score"], row["element_id"]))[:top_k]

    def expand(self, path, sections, top_k=20):
        data = self.by_page.get(path, {})
        return {requested: (data[stored][:top_k] if isinstance(data[stored], list) else data[stored])
                for requested in sections if (stored := ALIASES.get(requested, requested)) in data}
