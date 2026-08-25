class ContextRetrievalService:
    def __init__(self,compiled):
        self.compiled=compiled
        self.pages={p.path:p for p in compiled["pages"]}
        self.contexts={c.path:c for c in compiled["contexts"]}
        self.pidx=compiled["page_index"]; self.eidx=compiled["element_index"]
        self.graph=compiled["graph"]; self.backrefs=compiled["backrefs"]

    def data_search(self,query,scope=None,types=None,top_k=8):
        """
        Bundle retrieval:
        1) lexical/exact/facet seed retrieval
        2) machine-side one-hop typed-reference completion
        3) machine-side back-reference completion
        This is NOT LLM graph traversal.
        """
        seed_hits=self.pidx.search(query,types,scope,top_k)
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
                    from enterprise_data_context.models import SearchHit
                    chosen[target]=SearchHit(
                        target,tp.context_type,tp.name,max(0.25,h.score*0.75),
                        [f"reference:{ref.get('relation')}"],tp.l0,tp.l1
                    )

            # Backrefs are also useful, e.g. model -> metrics/purposes or metric <- purpose.
            for br in self.backrefs.get(h.path,[]):
                source=br.get("source")
                if source in self.pages and source not in chosen:
                    sp=self.pages[source]
                    from enterprise_data_context.models import SearchHit
                    chosen[source]=SearchHit(
                        source,sp.context_type,sp.name,max(0.20,h.score*0.55),
                        [f"backref:{br.get('relation')}"],sp.l0,sp.l1
                    )

        # Preserve seed relevance while allowing complementary referenced pages.
        hits=sorted(chosen.values(),key=lambda x:(-x.score,x.path))[:max(top_k,len(seed_hits))]
        pages=[self.pages[h.path] for h in hits]
        keys=["business_meaning","purpose","business_object","metrics","dimensions","models","fields","grain","lineage"]
        coverage={k:any(p.coverage.get(k,False) for p in pages) for k in keys}
        return {"query":query,"scope":scope or {},"contexts":[h.__dict__ for h in hits],"coverage_hint":coverage}

    def data_read(self,path,level="L1",sections=None):
        p=self.pages[path]
        if level.upper()=="L0": return {"path":path,"level":"L0","content":p.l0}
        if level.upper()=="L2":
            data=p.l2 if not sections else {k:v for k,v in p.l2.items() if k in sections}
            return {"path":path,"level":"L2","content":data}
        return {"path":path,"level":"L1","content":p.l1,"coverage":p.coverage}

    def data_expand(self,paths,expand,top_k=20):
        out={}
        for path in paths:
            page=self.pages[path]; item=self.eidx.expand(path,expand)
            for what in expand:
                if what=="backrefs": item[what]=self.backrefs.get(path,[])[:top_k]
                elif what=="lineage": item[what]=self.graph.neighbors(path)[:top_k]
                elif what=="impact": item[what]=self.graph.impact(path)[:top_k]
                elif what=="business_mapping":
                    item[what]={k:page.l2.get(k) for k in ("primary_objects","related_objects","object_attributes","topic_domain","topic")}
            out[path]=item
        return out

    def data_source(self,path,section=None):
        c=self.contexts[path]
        evidence=c.evidence.get(section,[]) if section else [e for xs in c.evidence.values() for e in xs]
        return [{
            "source_id":e.source.source_id,"path":e.source.path,"sheet":e.source.sheet,
            "section":e.source.section,"table":e.source.table,"row":e.source.row,
            "column":e.source.column,"cell":e.source.cell,"note":e.note
        } for e in evidence]
