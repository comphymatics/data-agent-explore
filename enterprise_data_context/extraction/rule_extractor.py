from __future__ import annotations
import re, uuid
from enterprise_data_context.models import ContextFragment, Evidence, TypedReference, SourceLocation
from .profiles import PROFILES

def norm(x):
    return re.sub(r"[\s_\-:/（）()]+", "", str(x or "").strip().lower())

def split_values(v):
    if v is None: return []
    if isinstance(v, list): return v
    return [x.strip() for x in re.split(r"[,;，；\n|]+", str(v)) if x.strip()]

def column_map(headers, profile):
    normalized = {norm(h): i for i, h in enumerate(headers)}
    out = {}
    for key, aliases in profile.aliases.items():
        for alias in aliases:
            a = norm(alias)
            # exact first, then contained header such as "模型 / Model Name".
            if a in normalized:
                out[key] = normalized[a]; break
            hit = next((i for h, i in normalized.items() if a and (a in h or h in a)), None)
            if hit is not None:
                out[key] = hit; break
    return out

class RuleExtractor:
    def __init__(self, profiles=None):
        self.profiles = profiles or PROFILES

    def extract(self, doc):
        out = []
        for elem in doc.elements:
            if elem.type != "table" or not elem.headers:
                continue
            for profile in self.profiles:
                if profile.source_types and doc.source_type not in profile.source_types:
                    continue
                cols = column_map(elem.headers, profile)
                if not all(k in cols for k in profile.required):
                    continue
                for offset, row in enumerate(elem.rows, 1):
                    def get(key):
                        i = cols.get(key)
                        if i is None or i >= len(row): return None
                        x = row[i]
                        return str(x).strip() if x is not None else None
                    name = get(profile.name_field)
                    if not name:
                        continue
                    src = elem.source
                    loc = SourceLocation(
                        source_id=src.source_id if src else doc.source_id,
                        path=src.path if src else doc.path,
                        sheet=src.sheet if src else None,
                        section=src.section if src else None,
                        table=src.table if src else None,
                        row=(src.row or 1) + offset if src else None
                    )
                    evidence = [Evidence(loc)]
                    out.append(ContextFragment(
                        str(uuid.uuid4()), profile.context_type, name, "identity", {"name":name},
                        source_type=doc.source_type, evidence=evidence
                    ))
                    for field, section in profile.sections.items():
                        v = get(field)
                        if not v: continue
                        payload = split_values(v) if section in {
                            "dimensions","metrics","scenarios","attributes","grain"
                        } else v
                        out.append(ContextFragment(
                            str(uuid.uuid4()), profile.context_type, name, section, payload,
                            source_type=doc.source_type, evidence=evidence
                        ))
                    for field, (relation, target_type) in profile.refs.items():
                        v = get(field)
                        if not v: continue
                        refs = [
                            TypedReference(relation, x, target_type, evidence=evidence)
                            for x in split_values(v)
                        ]
                        out.append(ContextFragment(
                            str(uuid.uuid4()), profile.context_type, name, "references", [],
                            source_type=doc.source_type, references=refs, evidence=evidence
                        ))
        return out
