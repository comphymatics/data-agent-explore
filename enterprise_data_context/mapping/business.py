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
    (r"(rsrp|rsrq|sinr|coverage|覆盖|mr)", ("Performance","Wireless Coverage")),
    (r"(handover|切换)", ("Performance","Wireless Performance")),
    (r"(alarm|告警)", ("Incident","Network Incident")),
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

        # Conservative rule mapping from model name + known fields.
        text = " ".join([ctx.name] + [str(x) for x in ctx.sections.get("important_fields",[])])
        objects=[]
        for pat,obj in self.field_rules:
            if re.search(pat, text, re.I):
                objects.append(obj)
        if objects and "primary_objects" not in ctx.sections:
            ctx.sections["primary_objects"] = [objects[0]]
            if len(objects)>1:
                ctx.sections["related_objects"] = list(dict.fromkeys(objects[1:]))

        if "topic" not in ctx.sections:
            for pat,(domain,topic) in self.topic_rules:
                if re.search(pat, text, re.I):
                    ctx.sections.setdefault("topic_domain", domain)
                    ctx.sections.setdefault("topic", topic)
                    break
        return ctx
