from collections import defaultdict
class ElementIndex:
    def __init__(self):
        self.by_page=defaultdict(dict)

    def add(self,page):
        for section in ("important_fields","formula","dimensions","metrics","constraints","grain"):
            v=page.l2.get(section)
            if v not in (None,"",[],{}):
                self.by_page[page.path][section]=v

    def expand(self,path,sections):
        data=self.by_page.get(path,{})
        return {s:data.get(s) for s in sections if s in data}
