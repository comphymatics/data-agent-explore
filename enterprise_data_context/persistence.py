from pathlib import Path
import json
from dataclasses import asdict

def save_compiled(compiled,out_dir):
    out=Path(out_dir); out.mkdir(parents=True,exist_ok=True)
    for sub in ("document-ir","fragments","contexts","pages"):
        (out/sub).mkdir(exist_ok=True)
    for d in compiled["documents"]:
        (out/"document-ir"/f"{safe(d.source_id)}.json").write_text(json.dumps(asdict(d),ensure_ascii=False,indent=2),encoding="utf-8")
    for i,f in enumerate(compiled["fragments"]):
        (out/"fragments"/f"{i:06d}.json").write_text(json.dumps(asdict(f),ensure_ascii=False,indent=2),encoding="utf-8")
    for c in compiled["contexts"]:
        (out/"contexts"/f"{safe(c.canonical_id)}.json").write_text(json.dumps(asdict(c),ensure_ascii=False,indent=2),encoding="utf-8")
    for p in compiled["pages"]:
        (out/"pages"/f"{safe(p.canonical_id)}.json").write_text(json.dumps(asdict(p),ensure_ascii=False,indent=2),encoding="utf-8")
    (out/"quality.json").write_text(json.dumps(compiled["quality_issues"],ensure_ascii=False,indent=2),encoding="utf-8")

def safe(x):
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in x)
