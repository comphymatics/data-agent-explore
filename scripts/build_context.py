import argparse, json
from enterprise_data_context.source_registry import load_sources
from enterprise_data_context.compiler import ContextCompiler
from enterprise_data_context.persistence import save_compiled

p=argparse.ArgumentParser()
p.add_argument("--source-dir",default="source-materials")
p.add_argument("--out",default="generated")
a=p.parse_args()

sources=load_sources(a.source_dir)
compiled=ContextCompiler().compile(sources)
save_compiled(compiled,a.out)
print(json.dumps({
    "sources":len(sources),"documents":len(compiled["documents"]),
    "fragments":len(compiled["fragments"]),"contexts":len(compiled["contexts"]),
    "quality_issues":len(compiled["quality_issues"])
},ensure_ascii=False,indent=2))
