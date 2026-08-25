import json
from pathlib import Path

class BuildState:
    def __init__(self,path):
        self.path=Path(path); self.data={"sources":{}}
        if self.path.exists():
            self.data=json.loads(self.path.read_text(encoding="utf-8"))

    def changed(self,source):
        prev=self.data["sources"].get(source["id"])
        return not prev or prev.get("fingerprint")!=source.get("fingerprint")

    def update(self,source,canonical_ids):
        self.data["sources"][source["id"]]={"fingerprint":source.get("fingerprint"),"canonical_ids":canonical_ids}

    def save(self):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        self.path.write_text(json.dumps(self.data,ensure_ascii=False,indent=2),encoding="utf-8")
