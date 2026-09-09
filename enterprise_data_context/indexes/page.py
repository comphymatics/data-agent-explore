import re, math
from collections import defaultdict, Counter
from enterprise_data_context.models import SearchHit
from .mention import MentionVocabulary, normalize, StablePosting

FACET_ALIASES={
    "classification.layer":"layer", "domain":"topic_domain",
    "scenario.kind":"scenario_kind",
}
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
    def __init__(self, encoder=None, mode="hybrid"):
        from .dense import configured_encoder
        self.encoder = encoder if encoder is not None else configured_encoder()
        self.mode = mode
        self.generation = 0
        self.vector_generation = -1
        self.vectors = {}
        self.last_warnings = []
        self.pages={}
        self.docs={}
        self.df=Counter()
        self.exact=defaultdict(StablePosting)
        self.mentions = MentionVocabulary()
        self.page_keys = {}
        self.postings = defaultdict(StablePosting)
        self.doc_lengths = {}
        self.total_length = 0

    def remove(self, path):
        for token in self.docs.pop(path, {}):
            self.df[token] -= 1
            self.postings[token].discard(path)
            if not self.postings[token]:
                del self.postings[token]
        for key in self.page_keys.pop(path, ()):
            self.exact[key].discard(path)
            self.mentions.remove(key)
            if not self.exact[key]:
                del self.exact[key]
        self.total_length -= self.doc_lengths.pop(path, 0)
        self.pages.pop(path, None)
        self.vectors.pop(path, None)
        self.generation += 1

    def add(self, page, extra_keys=()):
        if page.path in self.pages:
            self.remove(page.path)
        self.generation += 1
        self.pages[page.path] = page
        if page.identity_status in {"INFERRED", "CANDIDATE"}:
            return
        text = " ".join([page.name]+page.aliases+[page.l0, page.l1])
        tokens = toks(text); self.docs[page.path] = Counter(tokens)
        self.doc_lengths[page.path] = len(tokens)
        self.total_length += len(tokens)
        for token in set(tokens):
            self.df[token] += 1
            self.postings[token].add(page.path)
        self.add_exact_keys(page.path, [page.name, page.canonical_id, page.path, *page.aliases, *extra_keys])

    def add_exact_keys(self, path, keys):
        owned = self.page_keys.setdefault(path, set())
        for key in map(normalize, keys):
            if key and key not in owned:
                owned.add(key)
                self.exact[key].add(path)
                self.mentions.add(key)

    def validate(self):
        expected = {key: set() for keys in self.page_keys.values() for key in keys}
        for path, keys in self.page_keys.items():
            for key in keys:
                expected[key].add(path)
        missing_keys = any(not {normalize(k) for k in [page.name, page.canonical_id, page.path, *page.aliases] if k} <= self.page_keys.get(path, set())
                           for path, page in self.pages.items() if page.identity_status not in {"INFERRED", "CANDIDATE"})
        if missing_keys or not self.mentions.is_current() or expected != self.exact or {k: len(v) for k, v in expected.items()} != self.mentions.counts:
            return [{"severity": "error", "code": "exact_mention_index_stale"}]
        return []

    def search(self,query,types=None,scope=None,top_k=8, *, candidate_limit=None, allowed_paths=None, fallback_paths=()):
        if self.mode == "baseline" and candidate_limit is None:
            return self.baseline_search(query,types,scope,top_k)
        from .hybrid import hybrid_search
        return hybrid_search(self,query,types,scope,top_k, candidate_limit=candidate_limit, allowed_paths=allowed_paths, fallback_paths=fallback_paths)

    def baseline_search(self,query,types=None,scope=None,top_k=8,candidate_paths=None):
        types=set(types or []); scope=scope or {}
        q=toks(query); N=max(1,len(self.docs)); scores=defaultdict(float); reasons=defaultdict(list)
        qlower=query.lower().strip()
        for p in self.docs if candidate_paths is None else candidate_paths:
            tf=self.docs[p]
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
    return bool(target) and any(str(value or "").strip().casefold()==target for value in values)
