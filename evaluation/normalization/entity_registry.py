from collections import defaultdict
import unicodedata
from evaluation.benchmark.result_contract import ENTITY_TYPES


def normalized(value):
    return " ".join(unicodedata.normalize("NFKC",str(value)).casefold().split())


class EntityRegistry:
    """Never passed to adapters. Ambiguous aliases are retained as unresolved."""
    def __init__(self, rows):
        self.entities={}; self.aliases=defaultdict(set)
        for row in rows:
            cid=row["canonical_id"]; typ=row["type"]
            if not isinstance(cid,str) or ":" not in cid or typ not in ENTITY_TYPES or cid in self.entities:
                raise ValueError("registry needs unique stable canonical IDs and valid types")
            self.entities[cid]=row
            for alias in [cid,*row.get("aliases",[])]:
                self.aliases[normalized(alias)].add(cid)

    def resolve(self, value, typ=None):
        candidates=self.aliases.get(normalized(value),set())
        if typ:
            candidates={c for c in candidates if self.entities[c]["type"]==typ}
        return next(iter(candidates)) if len(candidates)==1 else None
