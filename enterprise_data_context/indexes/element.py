from collections import defaultdict
from hashlib import sha256
import json
from .page import toks

ALIASES = {"fields": "important_fields", "counters": "metric_catalog"}
SECTIONS = ("important_fields", "formula", "dimensions", "metrics", "constraints", "grain",
            "attributes", "measurement_point", "record_sources", "metric_catalog",
            "joins", "runtime_details", "primary_objects", "object_attributes")


class ElementIndex:
    """Searchable governed elements, always scoped to parent rich pages."""
    def __init__(self):
        self.by_page = defaultdict(dict)
        self.records = {}
        self.postings = defaultdict(set)

    def add(self, page):
        for eid in [eid for eid, row in self.records.items() if row["path"] == page.path]:
            self.records.pop(eid)
            for ids in self.postings.values():
                ids.discard(eid)
        self.by_page.pop(page.path, None)
        if page.identity_status in {"INFERRED", "CANDIDATE"}:
            return
        for section in SECTIONS:
            value = page.l2.get(section)
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
                       "offset": offset, "value": element, "status": status}
                self.records[eid] = row
                for token in set(toks(text)):
                    self.postings[token].add(eid)

    def search(self, query, paths, sections=None, top_k=20):
        if not isinstance(query, str) or not query.strip() or top_k < 1:
            raise ValueError("element search requires a query and positive top_k")
        terms = set(toks(query))
        allowed = {ALIASES.get(section, section) for section in (sections or [])}
        ids = set().union(*(self.postings.get(t, set()) for t in terms)) if terms else set()
        rows = []
        for eid in ids:
            row = self.records[eid]
            if row["path"] not in paths or (allowed and row["section"] not in allowed):
                continue
            text = json.dumps(row["value"], ensure_ascii=False).casefold()
            score = len(terms & set(toks(text)))/max(1, len(terms)) + (query.casefold() in text)
            rows.append({**row, "score": score})
        return sorted(rows, key=lambda row: (-row["score"], row["element_id"]))[:top_k]

    def expand(self, path, sections, top_k=20):
        data = self.by_page.get(path, {})
        return {requested: (data[stored][:top_k] if isinstance(data[stored], list) else data[stored])
                for requested in sections if (stored := ALIASES.get(requested, requested)) in data}
