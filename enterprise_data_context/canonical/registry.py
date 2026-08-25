import re
from collections import defaultdict

def normalize(text):
    return re.sub(r"[\s_\-:/（）()]+", "", str(text or "").strip().lower())

def slug(text):
    s = str(text).strip().lower()
    s = re.sub(r"[\s_]+", "-", s)
    s = re.sub(r"[^a-z0-9\u4e00-\u9fff\-]+", "", s)
    return re.sub(r"-+", "-", s).strip("-") or "unknown"

class CanonicalRegistry:
    def __init__(self):
        self.by_id = {}
        self.by_identity = defaultdict(list)
        self.by_alias = defaultdict(list)

    def path_for(self, typ, name):
        folder = {
            "analysis-purpose":"purposes","business-object":"business-objects",
            "logical-model":"logical-models","physical-model":"physical-models"
        }.get(typ, typ + "s")
        return f"data://{folder}/{slug(name)}"

    def register(self, ctx):
        self.by_id[ctx.canonical_id] = ctx
        self.by_identity[(ctx.context_type, normalize(ctx.name))].append(ctx.canonical_id)
        for a in ctx.aliases:
            self.by_alias[(ctx.context_type, normalize(a))].append(ctx.canonical_id)

    def lookup(self, typ, name):
        ids = self.by_identity.get((typ, normalize(name)), [])
        if len(ids)==1: return self.by_id[ids[0]]
        ids = self.by_alias.get((typ, normalize(name)), [])
        if len(ids)==1: return self.by_id[ids[0]]
        return None
