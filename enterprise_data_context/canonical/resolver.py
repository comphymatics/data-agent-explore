from enterprise_data_context.models import CanonicalContext
from .registry import CanonicalRegistry, slug, normalize

class CanonicalResolver:
    def __init__(self, registry=None):
        self.registry = registry or CanonicalRegistry()

    def resolve(self, fragment):
        exact = self.registry.lookup(fragment.context_type, fragment.candidate_name)
        if exact:
            return "SAME", exact, 1.0

        # Feature matching is conservative: requires same type, strong normalized-name overlap
        # plus at least one shared explicit feature.
        n = normalize(fragment.candidate_name)
        for ctx in self.registry.by_id.values():
            if ctx.context_type != fragment.context_type:
                continue
            cn = normalize(ctx.name)
            if n and cn and (n in cn or cn in n):
                shared = False
                for k, v in fragment.features.items():
                    if k in ctx.sections and ctx.sections[k] == v:
                        shared = True; break
                if shared:
                    return "SAME", ctx, 0.88

        return "DIFFERENT", None, 0.0

    def resolve_or_create(self, fragment):
        decision, ctx, _ = self.resolve(fragment)
        if decision == "SAME":
            return ctx
        base = f"{fragment.context_type}:{slug(fragment.candidate_name)}"
        cid = base
        i = 2
        while cid in self.registry.by_id:
            cid = f"{base}-{i}"; i += 1
        ctx = CanonicalContext(cid, fragment.context_type, fragment.candidate_name,
                               self.registry.path_for(fragment.context_type, fragment.candidate_name),
                               aliases=list(dict.fromkeys(fragment.aliases)))
        self.registry.register(ctx)
        return ctx
