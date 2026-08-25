from .authority import SourceAuthorityPolicy

LIST_SECTIONS = {
    "dimensions","metrics","scenarios","analysis_purposes","attributes",
    "important_fields","primary_objects","related_objects","constraints",
    "lineage.upstream","lineage.downstream","grain"
}

def dedupe(seq):
    out=[]; seen=set()
    for x in seq:
        k=repr(x)
        if k not in seen:
            seen.add(k); out.append(x)
    return out

class MergeEngine:
    def __init__(self, authority=None):
        self.authority = authority or SourceAuthorityPolicy()
        self.scalar_sources = {}

    def merge(self, ctx, frag):
        if frag.section_type == "identity":
            return
        if frag.section_type == "references":
            ctx.references.extend(frag.references)
            return

        sec, incoming = frag.section_type, frag.payload
        current = ctx.sections.get(sec)

        if sec in LIST_SECTIONS:
            left = current if isinstance(current,list) else ([] if current is None else [current])
            right = incoming if isinstance(incoming,list) else [incoming]
            ctx.sections[sec] = dedupe(left+right)
        elif current is None:
            ctx.sections[sec] = incoming
            self.scalar_sources[(ctx.canonical_id,sec)] = frag.source_type
        elif current == incoming:
            pass
        else:
            old_src = self.scalar_sources.get((ctx.canonical_id,sec),"unknown")
            old_rank = self.authority.rank(sec, old_src)
            new_rank = self.authority.rank(sec, frag.source_type)
            if new_rank > old_rank:
                ctx.conflicts.append({"section":sec,"kept":incoming,"discarded":current,
                                      "kept_source":frag.source_type,"discarded_source":old_src})
                ctx.sections[sec] = incoming
                self.scalar_sources[(ctx.canonical_id,sec)] = frag.source_type
            else:
                ctx.conflicts.append({"section":sec,"kept":current,"discarded":incoming,
                                      "kept_source":old_src,"discarded_source":frag.source_type})

        ctx.evidence.setdefault(sec, []).extend(frag.evidence)
        ctx.references.extend(frag.references)
