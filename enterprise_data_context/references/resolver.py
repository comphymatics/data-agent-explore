class ReferenceResolver:
    def __init__(self, registry):
        self.registry = registry

    def resolve_context(self, ctx):
        for ref in ctx.references:
            if ref.status == "CONFIRMED" and ref.target_path:
                continue
            if ref.status == "CANDIDATE":
                # Candidate provenance is a hard boundary. We may bind it to an
                # existing canonical target for review, but exact name resolution
                # must never promote an LLM/similarity proposal to a fact.
                if ref.target_type and not ref.target_path:
                    target = self.registry.lookup(ref.target_type, ref.raw_target)
                    if target and target.identity_status in {"EXPLICIT", "DERIVED"}:
                        ref.target_path = target.path
                continue
            if ref.target_type:
                target = self.registry.lookup(ref.target_type, ref.raw_target)
                if target and target.identity_status in {"EXPLICIT", "DERIVED"}:
                    ref.status = "CONFIRMED"
                    ref.target_path = target.path
                    ref.confidence = 1.0
                else:
                    ref.status = "UNRESOLVED"
        return ctx

def build_backrefs(contexts):
    out={}
    for c in contexts:
        if c.identity_status in {"INFERRED","CANDIDATE"}:
            continue
        for r in c.references:
            if r.status=="CONFIRMED" and r.target_path:
                out.setdefault(r.target_path,[]).append({"source":c.path,"relation":r.relation})
    return out
