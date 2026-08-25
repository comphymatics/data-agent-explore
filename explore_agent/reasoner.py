class JointReasoner:
    """
    Deterministic joint-reasoning baseline. An LLM reasoner can replace this contract,
    but Explore never receives raw documents or raw graph storage.
    """
    def summarize(self,query,hits,expansions):
        by_type={}
        for h in hits:
            by_type.setdefault(h["context_type"],[]).append(h["name"])
        parts=[]
        for typ,names in by_type.items():
            parts.append(f"{typ}: {', '.join(names[:5])}")
        return "; ".join(parts) if parts else "No relevant Context Page was found in currently available sources."
