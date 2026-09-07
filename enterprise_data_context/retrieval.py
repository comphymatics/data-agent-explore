from __future__ import annotations

import json
from dataclasses import asdict
from hashlib import sha256
import math
import re
from collections import Counter

from enterprise_data_context.serving import BundleAssembler, rich_relations, support_facts
from enterprise_data_context.models import SearchHit
from enterprise_data_context.indexes.hierarchy import HierarchyIndex
from enterprise_data_context.indexes.element import ALIASES, SECTIONS


class ContextRetrievalService:
    def __init__(self,compiled):
        self.compiled=compiled
        self.pages={p.path:p for p in compiled["pages"]}
        self.contexts={c.path:c for c in compiled["contexts"]}
        self.pidx=compiled["page_index"]; self.eidx=compiled["element_index"]
        self.graph=compiled["graph"]; self.backrefs=compiled["backrefs"]
        self.hierarchy=compiled.get("hierarchy") or HierarchyIndex().project(compiled["contexts"])
        self.association_report=dict(compiled.get("association_report",{}))
        self.index_version=compiled.get("index_version") or "context-memory-"+sha256(json.dumps(
            {"contexts":[asdict(c) for c in compiled["contexts"]],"coverage_declaration":compiled.get("coverage_declaration")},
            sort_keys=True,ensure_ascii=False).encode()).hexdigest()[:16]
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
        intent=None,
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
        assembler=BundleAssembler()
        candidates=assembler.complete(self,seed_hits,intent,types,scope)

        # Preserve seed relevance while allowing complementary referenced pages.
        limit=bundle_k if bundle_k is not None else max(top_k,top_k*2)

        ranked=assembler.rank(self,candidates,seed_hits)
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
            "anchor_context_ids":[h.path for h in seed_hits[:top_k]],
            "anchor_candidates":[{"path":h.path,"name":h.name,"rank":i+1} for i,h in enumerate(seed_hits[:top_k])],
            "retrieval_version":"page-serving/v3:"+self.pidx.mode+":"+getattr(self.pidx.encoder,"version","custom"),
            "encoder_version":getattr(self.pidx.encoder,"version","custom"),
            "truncated":bool(truncation_reasons),
            "truncation_reasons":truncation_reasons,
            "index_version":self.index_version,
            "warnings":warnings+getattr(self.pidx,"last_warnings",[]),
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
            "association_summary":{
                key:self.association_report.get(key)
                for key in (
                    "reference_count", "references_by_status",
                    "cross_source_confirmed_count", "orphan_context_count",
                )
            },
        }

    def _serialize_hit(self,hit,read_content,remaining_tokens):
        ctx=self.contexts[hit.path]
        hints={k:v for k,v in ctx.identity_hints.items() if k in {
            "stable_id","identity_namespace","environment_id","strong_key"}}
        identity={"keys":hints,"status":ctx.identity_status,
                  "evidence":[asdict(e) for e in ctx.evidence.get("identity",[])]} if hints else None
        if read_content is None:
            row=dict(hit.__dict__)
            row["support"] = support_facts(self.pages[hit.path],self.contexts[hit.path])
            row["knowledge_layer"] = "REFERENCE"
            if identity:
                row["binding_identity"] = identity
            return row,_estimate_tokens(json.dumps(row,ensure_ascii=False))

        base={
            "path":hit.path,"context_type":hit.context_type,"name":hit.name,
            "score":hit.score,"reasons":list(hit.reasons),
        }
        if identity:
            base["binding_identity"] = identity
        levels=("L1","L0") if read_content=="auto" else (read_content,)
        for level in levels:
            content=hit.l1 if level=="L1" else hit.l0
            support=support_facts(self.pages[hit.path],self.contexts[hit.path],level)
            estimated=_estimate_tokens(json.dumps({**base,"content":content,"support":support},ensure_ascii=False))
            if remaining_tokens is None or estimated <= remaining_tokens:
                return {
                    **base,"content_level":level,"content":content,
                    "estimated_tokens":estimated,"support":support,"knowledge_layer":"REFERENCE",
                },estimated
        return None,0

    def data_read(self,path,level="L1",sections=None):
        if path not in self.pages:
            if self.hierarchy.has(path):
                return {
                    "path":path,
                    "level":"HIERARCHY",
                    "content":self.hierarchy.describe(path),
                }
            raise KeyError(f"unknown context path: {path}")
        p=self.pages[path]
        if level.upper()=="L0":
            return {"path":path,"level":"L0","content":p.l0,"hierarchy":p.hierarchy}
        if level.upper()=="L2":
            data=p.l2 if not sections else {k:v for k,v in p.l2.items() if k in sections}
            return {
                "path":path,"level":"L2","content":data,
                "section_status":p.section_status,
                "references":p.references,
                "candidates":p.candidates,
                "conflicts":p.conflicts,
                "hierarchy":p.hierarchy,
            }
        return {
            "path":path,"level":"L1","content":p.l1,"coverage":p.coverage,
            "references":p.references,
            "candidate_count":sum(len(x) for x in p.candidates.values()),
            "conflict_count":len(p.conflicts),
            "hierarchy":p.hierarchy,
        }

    def data_expand(self,paths,expand,top_k=20,query=None,intent=None,token_budget=None):
        if top_k < 1 or (token_budget is not None and token_budget < 1):
            raise ValueError("expansion budgets must be positive")
        out={}
        for path in paths:
            if path not in self.pages and not self.hierarchy.has(path):
                raise KeyError(f"unknown context path: {path}")
            page=self.pages.get(path)
            item=self.eidx.expand(path,expand,top_k) if page else {}
            hierarchy=self.hierarchy.describe(path)
            for what in expand:
                if what=="backrefs": item[what]=rich_relations(self,path,"related",top_k,intent)["incoming"]
                elif what in {"lineage","related","impact"}:
                    item[what]=rich_relations(self,path,"lineage" if what=="impact" else what,top_k,intent)
                elif what=="parents": item[what]=hierarchy.get("parents",[])[:top_k]
                elif what=="children": item[what]=hierarchy.get("children",[])[:top_k]
                elif what=="hierarchy": item[what]=hierarchy
                elif what=="association_report": item[what]=dict(self.association_report)
                elif what=="business_mapping":
                    mapping={
                        k:page.l2.get(k)
                        for k in ("primary_objects","related_objects","object_attributes","topic_domain","topic")
                        if page and page.l2.get(k) not in (None,"",[],{})
                    }
                    if mapping:
                        item[what]=mapping
                elif what=="candidates": item[what]=page.candidates if page else {}
                elif what=="conflicts": item[what]=page.conflicts if page else []
                elif what=="evidence": item[what]=self.data_source(path) if page else []
            if page:
                section_totals={key:len(value) for key,value in self.eidx.by_page.get(path,{}).items() if isinstance(value,list)}
                item["section_totals"]=section_totals
                if any(section_totals.get(ALIASES.get(key,key),0)>top_k for key in expand):
                    item["truncated"]=True
                requested=list(SECTIONS) if "elements" in expand else [ALIASES.get(x,x) for x in expand]
                if "business_mapping" in expand:
                    requested += ["primary_objects","related_objects","object_attributes"]
                item["support"]=support_facts(page,self.contexts[path],sections=requested)
                if query:
                    item["elements"]=self.eidx.search(query,[path],expand,top_k)
                    for requested_section in expand:
                        stored=ALIASES.get(requested_section,requested_section)
                        focused=[e["value"] for e in item["elements"] if e["section"]==stored]
                        if focused and isinstance(item.get(requested_section),list):
                            item[requested_section]=focused
                    for element in item["elements"]:
                        element["evidence"]=self.data_source(path,element["section"])
                for proof in item.get("support",[]):
                    returned=next((v for k,v in item.items() if ALIASES.get(k,k)==proof["section"]),None)
                    if section_totals.get(proof["section"],0)>top_k or (isinstance(returned,list) and len(returned)<section_totals.get(proof["section"],0)):
                        proof["truncated"]=True
            out[path]=item
        if token_budget is not None:
            # Trim whole path payloads, then whole sections. Never cut an evidence assertion.
            used=0
            for path,item in list(out.items()):
                accepted={}
                for key,value in item.items():
                    cost=_estimate_tokens(json.dumps({key:value},ensure_ascii=False))
                    if used+cost <= token_budget:
                        accepted[key]=value; used+=cost
                    else:
                        accepted["truncated"]=True
                # A trimmed section cannot keep its support proof.
                if "support" in accepted:
                    accepted["support"]=[r for r in accepted["support"] if r["section"] in {ALIASES.get(k,k) for k in accepted} or
                        ("elements" in accepted and any(e["section"]==r["section"] for e in accepted["elements"])) or
                        (r["section"] in {"primary_objects","related_objects","object_attributes"} and "business_mapping" in accepted)]
                out[path]=accepted
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
