import argparse
import json

from enterprise_data_context.compiler import ContextCompiler
from enterprise_data_context.persistence import save_compiled


parser = argparse.ArgumentParser(description="Build Enterprise Data Context from the parser Template JSON delivery")
parser.add_argument("--input", required=True, help="Delivered Template JSON file or directory")
parser.add_argument("--out", default="generated")
args = parser.parse_args()

compiled = ContextCompiler().compile_template_inputs(args.input)
manifest = save_compiled(compiled, args.out)
print(json.dumps({
    **manifest,
    "template_input_files": compiled["template_input_files"],
    "delivery_report": compiled["delivery_report"],
}, ensure_ascii=False, indent=2))
