from __future__ import annotations
import re

DEFAULT_FIELD_OBJECT_RULES = [
    (r"\b(cell[_ ]?id|cgi|ecgi|eci)\b", "Cell"),
    (r"\b(imsi|msisdn|subscriber[_ ]?id)\b", "Subscriber"),
    (r"\b(imei|tac)\b", "Terminal"),
    (r"\b(site[_ ]?id|enodeb|gnodeb|ne[_ ]?id)\b", "Network Element"),
    (r"\b(grid[_ ]?id|longitude|latitude|lon|lat)\b", "Location"),
]
DEFAULT_TOPIC_RULES = [
    (r"(rsrp|rsrq|sinr|coverage|覆盖|mr)", ("性能","无线覆盖")),
    (r"(alarm|告警)", ("事件","网络事件")),
]

class BusinessSemanticMapper:
    def __init__(self, field_rules=None, topic_rules=None):
        self.field_rules = field_rules or DEFAULT_FIELD_OBJECT_RULES
        self.topic_rules = topic_rules or DEFAULT_TOPIC_RULES

    def apply(self, ctx, fragments):
        # Explicit mappings always win.
        for f in fragments:
            for key in ("primary_objects","related_objects","object_attributes","topic_domain","topic","grain"):
                v = f.features.get(key)
                if v and key not in ctx.sections:
                    ctx.sections[key] = v
                    ctx.section_status[key] = f.status
                    ctx.evidence.setdefault(key, []).extend(f.evidence)

        # Conservative rule mapping from model name + known fields.
        text = " ".join([ctx.name] + [str(x) for x in ctx.sections.get("important_fields",[])])
        objects=[]
        for pat,obj in self.field_rules:
            if re.search(pat, text, re.I):
                objects.append(obj)
        if objects and "primary_objects" not in ctx.sections:
            ctx.sections["primary_objects"] = [objects[0]]
            ctx.section_status["primary_objects"] = "DERIVED"
            ctx.evidence["primary_objects"] = self._input_evidence(fragments)
            if len(objects)>1:
                ctx.sections["related_objects"] = list(dict.fromkeys(objects[1:]))
                ctx.section_status["related_objects"] = "DERIVED"
                ctx.evidence["related_objects"] = self._input_evidence(fragments)

        if "topic" not in ctx.sections:
            for pat,(domain,topic) in self.topic_rules:
                if re.search(pat, text, re.I):
                    evidence = self._input_evidence(fragments)
                    payload_evidence = [self._dump_evidence(item) for item in evidence]
                    ctx.candidate_sections.setdefault("topic_domain", []).append({
                        "payload": domain, "status": "CANDIDATE", "confidence": 0.65,
                        "source_type": "deterministic_rule", "evidence": payload_evidence,
                    })
                    ctx.candidate_sections.setdefault("topic", []).append({
                        "payload": topic, "status": "CANDIDATE", "confidence": 0.65,
                        "source_type": "deterministic_rule", "evidence": payload_evidence,
                    })
                    break
        return ctx

    @staticmethod
    def _input_evidence(fragments):
        out=[]; seen=set()
        for fragment in fragments:
            for evidence in fragment.evidence:
                key=(
                    evidence.source.source_id, evidence.source.path,
                    evidence.source.sheet, evidence.source.section,
                    evidence.source.table, evidence.source.row,
                    evidence.source.column, evidence.source.cell,
                )
                if key not in seen:
                    seen.add(key); out.append(evidence)
        return out

    @staticmethod
    def _dump_evidence(evidence):
        return {
            "source_id": evidence.source.source_id,
            "path": evidence.source.path,
            "sheet": evidence.source.sheet,
            "section": evidence.source.section,
            "table": evidence.source.table,
            "row": evidence.source.row,
            "column": evidence.source.column,
            "cell": evidence.source.cell,
            "note": evidence.note,
        }
