from enterprise_data_context.hierarchy_config import load_hierarchy_config
import argparse, json
from enterprise_data_context.source_registry import load_sources
from enterprise_data_context.compiler import ContextCompiler
from enterprise_data_context.persistence import save_compiled

p=argparse.ArgumentParser()
p.add_argument("--source-dir",default="source-materials")
p.add_argument("--out",default="generated")
p.add_argument("--hierarchy-config", help="Semantic hierarchy policy JSON")
a=p.parse_args()

sources=load_sources(a.source_dir)
compiled=ContextCompiler(hierarchy_config=load_hierarchy_config(a.hierarchy_config)).compile(sources)
save_compiled(compiled,a.out)
print(json.dumps({
    "sources":len(sources),"documents":len(compiled["documents"]),
    "fragments":len(compiled["fragments"]),"contexts":len(compiled["contexts"]),
    "quality_issues":len(compiled["quality_issues"])
},ensure_ascii=False,indent=2))
