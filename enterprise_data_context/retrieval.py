from __future__ import annotations

import math
import re
from collections import Counter

from enterprise_data_context.models import SearchHit


class ContextRetrievalService:
    def __init__(self,compiled):
        self.compiled=compiled
        self.pages={p.path:p for p in compiled["pages"]}
        self.contexts={c.path:c for c in compiled["contexts"]}
        self.pidx=compiled["page_index"]; self.eidx=compiled["element_index"]
        self.graph=compiled["graph"]; self.backrefs=compiled["backrefs"]
        self.index_version=compiled.get("index_version")
        self.quality_issues=list(compiled.get("quality_issues",[]))

    def data_search(
        self,
        query,
        scope=None,
        types=None,
        top_k=8,
        bundle_k=None,
        token_budget=None,
        seen_context_ids=None,
        read_content=None,
        max_per_type=None,
    ):
        """
        Bundle retrieval:
        1) lexical/exact/facet seed retrieval
        2) machine-side one-hop typed-reference completion
        3) machine-side back-reference completion
        This is NOT LLM graph traversal.
        """
        if not isinstance(query,str) or not query.strip():
            raise ValueError("query must be a non-empty string")
        if top_k < 1:
            raise ValueError("top_k must be positive")
        if bundle_k is not None and bundle_k < 1:
            raise ValueError("bundle_k must be positive")
        if token_budget is not None and token_budget < 1:
            raise ValueError("token_budget must be positive")
        if max_per_type is not None and max_per_type < 1:
            raise ValueError("max_per_type must be positive")
        if read_content not in (None,"L0","L1","auto"):
            raise ValueError("read_content must be one of L0, L1, auto, or None")

        if seen_context_ids is not None and not isinstance(seen_context_ids,(list,tuple,set)):
            raise ValueError("seen_context_ids must be an array of context paths")
        seen_paths={path for path in (seen_context_ids or []) if path in self.pages}
        seed_limit=min(len(self.pages),top_k+len(seen_paths)) if seen_paths else top_k
        seed_hits=self.pidx.search(query,types,scope,seed_limit)
        chosen={}
        for h in seed_hits:
            chosen[h.path]=h

        # Complete the bundle with directly referenced rich contexts.
        for h in list(seed_hits):
            page=self.pages[h.path]
            for ref in page.references:
                target=ref.get("target_path")
                if ref.get("status")=="CONFIRMED" and target in self.pages and target not in chosen:
                    tp=self.pages[target]
                    chosen[target]=SearchHit(
                        target,tp.context_type,tp.name,max(0.25,h.score*0.75),
                        [f"reference:{ref.get('relation')}"],tp.l0,tp.l1
                    )

            # Backrefs are also useful, e.g. model -> metrics/purposes or metric <- purpose.
            for br in self.backrefs.get(h.path,[]):
                source=br.get("source")
                if source in self.pages and source not in chosen:
                    sp=self.pages[source]
                    chosen[source]=SearchHit(
                        source,sp.context_type,sp.name,max(0.20,h.score*0.55),
                        [f"backref:{br.get('relation')}"],sp.l0,sp.l1
                    )

        # Preserve seed relevance while allowing complementary referenced pages.
        limit=bundle_k if bundle_k is not None else max(top_k,top_k*2)
        limit=max(top_k,limit)
        ranked=sorted(chosen.values(),key=lambda x:(-x.score,x.path))
        effective_content="auto" if token_budget is not None and read_content is None else read_content
        type_counts=Counter(); hits=[]; serialized=[]; used_tokens=0
        truncation_reasons=[]; seen_skipped=0

        def mark_truncated(reason):
            if reason not in truncation_reasons:
                truncation_reasons.append(reason)

        for hit in ranked:
            if hit.path in seen_paths:
                seen_skipped += 1
                mark_truncated("seen_context")
                continue
            if len(hits) >= limit:
                mark_truncated("bundle_limit")
                continue
            if max_per_type is not None and type_counts[hit.context_type] >= max_per_type:
                mark_truncated("diversity_limit")
                continue

            remaining=None if token_budget is None else token_budget-used_tokens
            row,estimated_tokens=self._serialize_hit(hit,effective_content,remaining)
            if row is None:
                mark_truncated("token_budget")
                continue
            hits.append(hit); serialized.append(row)
            type_counts[hit.context_type] += 1
            used_tokens += estimated_tokens

        pages=[self.pages[h.path] for h in hits]
        keys=["business_meaning","purpose","business_object","metrics","dimensions","models","fields","grain","lineage"]
        coverage={k:any(p.coverage.get(k,False) for p in pages) for k in keys}
        selected_path_set={p.path for p in pages}
        warnings=[
            issue for issue in self.quality_issues
            if not issue.get("context") or issue.get("context") in selected_path_set
        ]
        selected_paths=[p.path for p in pages]
        all_seen=sorted(seen_paths | set(selected_paths))
        candidate_count=len(ranked)
        novel_candidate_count=candidate_count-seen_skipped
        return {
            "query":query,
            "scope":scope or {},
            "contexts":serialized,
            "coverage_hint":coverage,
            "truncated":bool(truncation_reasons),
            "truncation_reasons":truncation_reasons,
            "index_version":self.index_version,
            "warnings":warnings,
            "selected_context_ids":selected_paths,
            "seen_context_ids":all_seen,
            "budget":{
                "scope":"context_hydration",
                "token_budget":token_budget,
                "estimated_tokens":used_tokens,
                "remaining_tokens":None if token_budget is None else max(0,token_budget-used_tokens),
                "bundle_limit":limit,
                "max_contexts_per_type":max_per_type,
            },
            "novelty":{
                "candidate_count":candidate_count,
                "novel_candidate_count":novel_candidate_count,
                "selected_new_count":len(hits),
                "seen_skipped_count":seen_skipped,
                "candidate_novelty_ratio":(
                    novel_candidate_count/candidate_count if candidate_count else 0.0
                ),
            },
        }

    def _serialize_hit(self,hit,read_content,remaining_tokens):
        if read_content is None:
            row=dict(hit.__dict__)
            return row,_estimate_tokens(" ".join((hit.path,hit.name,hit.l0,hit.l1)))

        base={
            "path":hit.path,"context_type":hit.context_type,"name":hit.name,
            "score":hit.score,"reasons":list(hit.reasons),
        }
        levels=("L1","L0") if read_content=="auto" else (read_content,)
        for level in levels:
            content=hit.l1 if level=="L1" else hit.l0
            estimated=_estimate_tokens(" ".join((hit.path,hit.name," ".join(hit.reasons),content)))
            if remaining_tokens is None or estimated <= remaining_tokens:
                return {
                    **base,"content_level":level,"content":content,
                    "estimated_tokens":estimated,
                },estimated
        return None,0

    def data_read(self,path,level="L1",sections=None):
        if path not in self.pages:
            raise KeyError(f"unknown context path: {path}")
        p=self.pages[path]
        if level.upper()=="L0": return {"path":path,"level":"L0","content":p.l0}
        if level.upper()=="L2":
            data=p.l2 if not sections else {k:v for k,v in p.l2.items() if k in sections}
            return {
                "path":path,"level":"L2","content":data,
                "section_status":p.section_status,
                "references":p.references,
                "candidates":p.candidates,
                "conflicts":p.conflicts,
            }
        return {
            "path":path,"level":"L1","content":p.l1,"coverage":p.coverage,
            "references":p.references,
            "candidate_count":sum(len(x) for x in p.candidates.values()),
            "conflict_count":len(p.conflicts),
        }

    def data_expand(self,paths,expand,top_k=20):
        out={}
        for path in paths:
            if path not in self.pages:
                raise KeyError(f"unknown context path: {path}")
            page=self.pages[path]; item=self.eidx.expand(path,expand)
            for what in expand:
                if what=="backrefs": item[what]=self.backrefs.get(path,[])[:top_k]
                elif what=="lineage":
                    item[what]={
                        "outgoing":self.graph.neighbors(path,"out")[:top_k],
                        "incoming":self.graph.neighbors(path,"in")[:top_k],
                    }
                elif what=="impact": item[what]=self.graph.impact(path)[:top_k]
                elif what=="business_mapping":
                    mapping={
                        k:page.l2.get(k)
                        for k in ("primary_objects","related_objects","object_attributes","topic_domain","topic")
                        if page.l2.get(k) not in (None,"",[],{})
                    }
                    if mapping:
                        item[what]=mapping
                elif what=="candidates": item[what]=page.candidates
                elif what=="conflicts": item[what]=page.conflicts
                elif what=="evidence": item[what]=self.data_source(path)
            out[path]=item
        return out

    def data_source(self,path,section=None):
        if path not in self.contexts:
            raise KeyError(f"unknown context path: {path}")
        c=self.contexts[path]
        evidence=c.evidence.get(section,[]) if section else [e for xs in c.evidence.values() for e in xs]
        return [{
            "source_id":e.source.source_id,"path":e.source.path,"sheet":e.source.sheet,
            "section":e.source.section,"table":e.source.table,"row":e.source.row,
            "column":e.source.column,"cell":e.source.cell,"note":e.note,
            "section_status":c.section_status.get(section) if section else None,
        } for e in evidence]


def _estimate_tokens(value):
    """Deterministic conservative estimate; this is a budget guard, not a tokenizer."""
    text=str(value or "")
    cjk=len(re.findall(r"[\u3400-\u9fff]",text))
    non_cjk=len(re.sub(r"[\u3400-\u9fff\s]","",text))
    return max(1,cjk+math.ceil(non_cjk/4))
