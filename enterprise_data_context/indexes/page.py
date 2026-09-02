import re, math
from collections import defaultdict, Counter
from enterprise_data_context.models import SearchHit

FACET_ALIASES={"classification.layer":"layer","domain":"topic_domain"}
CLASSIFICATION_FILTERS={"layer","topic_domain","topic"}

def toks(s):
    # identifiers/English plus Chinese bigrams for a lightweight lexical baseline.
    s=str(s or "").lower()
    xs=re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]+",s)
    out=[]
    for x in xs:
        if re.fullmatch(r"[\u4e00-\u9fff]+",x) and len(x)>1:
            out += [x[i:i+2] for i in range(len(x)-1)]
        else:
            out.append(x)
    return out

class PageIndex:
    def __init__(self):
        self.pages={}
        self.docs={}
        self.df=Counter()
        self.exact=defaultdict(set)

    def add(self,page):
        self.pages[page.path]=page
        if page.identity_status in {"INFERRED","CANDIDATE"}:
            return
        text=" ".join([page.name]+page.aliases+[page.l0,page.l1])
        tokens=toks(text); self.docs[page.path]=Counter(tokens)
        for t in set(tokens): self.df[t]+=1
        for k in [page.name,page.canonical_id]+page.aliases:
            self.exact[str(k).lower()].add(page.path)

    def search(self,query,types=None,scope=None,top_k=8):
        types=set(types or []); scope=scope or {}
        q=toks(query); N=max(1,len(self.docs)); scores=defaultdict(float); reasons=defaultdict(list)
        qlower=query.lower().strip()
        for p,tf in self.docs.items():
            page=self.pages[p]
            if types and page.context_type not in types: continue
            governed_scope={FACET_ALIASES.get(k,k):v for k,v in scope.items() if FACET_ALIASES.get(k,k) in CLASSIFICATION_FILTERS}
            if page.context_type in {"physical-model","logical-model"} and any(
                not facet_matches(page.facets.get(key),value) for key,value in governed_scope.items()
            ):
                continue
            score=0.0
            if p in self.exact.get(qlower,[]):
                score+=15; reasons[p].append("exact")
            lexical_score=0.0
            for token in q:
                if tf[token]:
                    idf=math.log((N+1)/(1+self.df[token]))+1
                    lexical_score += (1+math.log(tf[token]))*idf
            if lexical_score:
                score+=lexical_score; reasons[p].append("lexical")
            if score:
                scores[p]+=score
            for k,v in scope.items():
                facet=FACET_ALIASES.get(k,k)
                if facet in page.facets and facet_matches(page.facets[facet],v):
                    scores[p]+=3.0 if facet in CLASSIFICATION_FILTERS else 1.5
                    reasons[p].append(f"scope:{facet}")
                elif facet not in CLASSIFICATION_FILTERS and str(v).lower() in page.l1.lower():
                    scores[p]+=1.5; reasons[p].append(f"scope:{facet}")
        ranked=sorted(scores,key=lambda p:(-scores[p],p))
        return [
            SearchHit(p,self.pages[p].context_type,self.pages[p].name,scores[p],reasons[p],
                      self.pages[p].l0,self.pages[p].l1)
            for p in ranked[:top_k]
        ]


def facet_matches(actual, expected):
    values=actual if isinstance(actual,list) else [actual]
    target=str(expected or "").strip().casefold()
    return any(str(value or "").strip().casefold()==target for value in values)
