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
        self.by_hint = defaultdict(list)

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
        for key, value in ctx.identity_hints.items():
            if value:
                self.by_hint[(ctx.context_type, key, normalize(value))].append(ctx.canonical_id)

    def add_aliases_and_hints(self, ctx, aliases=None, identity_hints=None):
        for alias in aliases or []:
            if alias and alias not in ctx.aliases:
                ctx.aliases.append(alias)
                self.by_alias[(ctx.context_type, normalize(alias))].append(ctx.canonical_id)
        for key, value in (identity_hints or {}).items():
            if not value:
                continue
            existing = ctx.identity_hints.get(key)
            if existing and normalize(existing) != normalize(value):
                continue
            if not existing:
                ctx.identity_hints[key] = value
                self.by_hint[(ctx.context_type, key, normalize(value))].append(ctx.canonical_id)

    def lookup_hint(self, typ, identity_hints):
        matches = set()
        for key, value in identity_hints.items():
            ids = self.by_hint.get((typ, key, normalize(value)), [])
            matches.update(ids)
        if len(matches) == 1:
            return self.by_id[next(iter(matches))]
        return None

    def lookup_candidates(self, typ, name):
        ids = set(self.by_identity.get((typ, normalize(name)), []))
        ids.update(self.by_alias.get((typ, normalize(name)), []))
        return [self.by_id[x] for x in sorted(ids)]

    def lookup(self, typ, name):
        candidates = self.lookup_candidates(typ, name)
        if len(candidates) == 1:
            return candidates[0]
        return None
