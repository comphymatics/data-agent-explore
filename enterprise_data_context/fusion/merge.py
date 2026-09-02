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
        if frag.status in {"INFERRED", "CANDIDATE"}:
            evidence = [
                {
                    "source_id": e.source.source_id,
                    "path": e.source.path,
                    "sheet": e.source.sheet,
                    "section": e.source.section,
                    "table": e.source.table,
                    "row": e.source.row,
                    "column": e.source.column,
                    "cell": e.source.cell,
                    "note": e.note,
                }
                for e in frag.evidence
            ]
            ctx.candidate_sections.setdefault(frag.section_type, []).append({
                "payload": frag.payload,
                "status": frag.status,
                "confidence": frag.confidence,
                "source_type": frag.source_type,
                "evidence": evidence,
            })
            for ref in frag.references:
                ref.status = "CANDIDATE"
                ctx.references.append(ref)
            return

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
            ctx.section_status[sec] = self._combined_status(
                ctx.section_status.get(sec), frag.status
            )
        elif current is None:
            ctx.sections[sec] = incoming
            self.scalar_sources[(ctx.canonical_id,sec)] = frag.source_type
            ctx.section_status[sec] = frag.status
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
                ctx.section_status[sec] = frag.status
            else:
                ctx.conflicts.append({"section":sec,"kept":current,"discarded":incoming,
                                      "kept_source":old_src,"discarded_source":frag.source_type})

        ctx.evidence.setdefault(sec, []).extend(frag.evidence)
        ctx.references.extend(frag.references)

    @staticmethod
    def _combined_status(current, incoming):
        rank = {"EXPLICIT": 3, "DERIVED": 2, "INFERRED": 1, "CANDIDATE": 0}
        if current is None:
            return incoming
        return current if rank[current] <= rank[incoming] else incoming
