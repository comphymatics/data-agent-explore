from enterprise_data_context.hierarchy_config import load_hierarchy_config
import argparse
import json

from enterprise_data_context.compiler import ContextCompiler
from enterprise_data_context.handoff import load_fragments
from enterprise_data_context.persistence import save_compiled


parser=argparse.ArgumentParser(
    description="Compatibility build from internal ContextFragment JSON/JSONL"
)
parser.add_argument("--fragments",required=True,help="Internal or legacy ContextFragment file")
parser.add_argument("--out",default="generated")
parser.add_argument("--hierarchy-config", help="Semantic hierarchy policy JSON")
args=parser.parse_args()

fragments=load_fragments(args.fragments)
compiled=ContextCompiler(hierarchy_config=load_hierarchy_config(args.hierarchy_config)).compile_fragments(fragments)
manifest=save_compiled(compiled,args.out)
print(json.dumps(manifest,ensure_ascii=False,indent=2))
