from collections import defaultdict, deque
class BackendGraph:
    def __init__(self):
        self.out=defaultdict(list); self.inc=defaultdict(list)

    def add(self,s,r,t):
        edge={"source":s,"relation":r,"target":t}
        if edge not in self.out[s]:
            self.out[s].append(edge); self.inc[t].append(edge)

    def project(self,contexts):
        for c in contexts:
            for r in c.references:
                if r.status=="CONFIRMED" and r.target_path:
                    self.add(c.path,r.relation,r.target_path)
            for sec,rel in (("lineage.upstream","upstream"),("lineage.downstream","downstream")):
                vals=c.sections.get(sec,[]) or []
                if not isinstance(vals,list): vals=[vals]
                for t in vals:
                    if isinstance(t,str) and t.startswith("data://"):
                        self.add(c.path,rel,t)
        return self

    def neighbors(self,path,direction="out"):
        return list(self.out[path] if direction=="out" else self.inc[path])

    def impact(self,path,max_depth=4):
        # downstream/back-reference impact using incoming references + downstream edges.
        seen={path}; q=deque([(path,0)]); out=[]
        while q:
            cur,d=q.popleft()
            if d>=max_depth: continue
            for e in self.inc[cur]:
                nxt=e["source"]
                if nxt not in seen:
                    seen.add(nxt); out.append(e); q.append((nxt,d+1))
        return out
