"""Rebuild only organization over a pinned canonical snapshot, optionally incrementally."""
import argparse
import json

from enterprise_data_context.hierarchy_config import load_hierarchy_config
from enterprise_data_context.inference.config import load_llm_inference_config
from enterprise_data_context.inference.provider import provider_from_config
from enterprise_data_context.organization import SemanticOrganizationBuilder
from enterprise_data_context.materialization.pages import PageMaterializer
from enterprise_data_context.indexes.page import PageIndex
from enterprise_data_context.indexes.element import ElementIndex
from enterprise_data_context.persistence import load_compiled, save_compiled
from enterprise_data_context.quality import validate_contexts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--previous-snapshot", help="Previous organization snapshot for dependency-aware updates")
    parser.add_argument("--config", required=True)
    parser.add_argument("--llm-config", help="Existing governed provider configuration; only used if llm_enabled")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    config = load_hierarchy_config(args.config)
    provider = None
    if config.get("llm_enabled"):
        if not args.llm_config:
            parser.error("llm_enabled requires --llm-config")
        llm = load_llm_inference_config(args.llm_config)
        provider = provider_from_config(llm)
        config["llm_model"] = llm.model
    compiled = load_compiled(args.snapshot)
    previous = load_compiled(args.previous_snapshot)["hierarchy"] if args.previous_snapshot else compiled["hierarchy"]
    organization = SemanticOrganizationBuilder(config, provider).build(compiled["contexts"], previous)
    compiled.update(organization)
    index = compiled["hierarchy"]
    materializer = PageMaterializer()
    compiled["pages"] = [materializer.materialize(c, index.describe(c.path) if config.get("hierarchy_enabled", True) else {}) for c in compiled["contexts"]]
    compiled["page_index"], compiled["element_index"] = PageIndex(), ElementIndex()
    for page in compiled["pages"]:
        compiled["page_index"].add(page)
        compiled["element_index"].add(page)
    compiled["quality_issues"] = validate_contexts(compiled["contexts"]) + index.validate()
    manifest = save_compiled(compiled, args.out)
    print(json.dumps({"manifest": manifest, "hierarchy_update": index.last_update}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
