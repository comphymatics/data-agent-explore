from collections import defaultdict
class ElementIndex:
    def __init__(self):
        self.by_page=defaultdict(dict)

    def add(self,page):
        for section in (
            "important_fields","formula","dimensions","metrics","constraints","grain",
            "attributes","measurement_point","record_sources","metric_catalog",
        ):
            v=page.l2.get(section)
            if v not in (None,"",[],{}):
                self.by_page[page.path][section]=v

    def expand(self,path,sections):
        data=self.by_page.get(path,{})
        aliases={"fields":"important_fields"}
        out={}
        for requested in sections:
            stored=aliases.get(requested,requested)
            if stored in data:
                out[requested]=data[stored]
        return out
