"""Structured, read-only diagnostics for internal profile adaptation."""
import json
from pathlib import Path
import yaml
from .contracts import fingerprint
from .source_inventory import inventory, inspect_raw_structure
from .mapping import parser_records
from .quality import validate_dataset, describe
from .raw_verifier import validate_case_sources


def load_dataset(directory):
    root=Path(directory)
    def read(name):
        content=(root/name).read_text()
        return yaml.safe_load(content) if name.endswith(".yaml") else json.loads(content)
    return {"cases":read("cases.draft.yaml")["cases"],"aliases":read("aliases.draft.yaml"),
            "entities":read("candidate_entities.json"),"relations":read("candidate_relations.json"),
            "source_map":read("source_entity_map.json"),"report":read("generation_report.json")}


def validate(directory):
    dataset=load_dataset(directory)
    result=validate_dataset(dataset["cases"],dataset["entities"],dataset["relations"],dataset["aliases"],dataset["report"]["raw_inventory"])
    for source in dataset["source_map"].values():
        if set(source["entity_ids"])-{e["id"] for e in dataset["entities"]}: raise ValueError("source map has dangling entities")
    result["warnings"]=describe(dataset["cases"],dataset["entities"],dataset["relations"],dataset["aliases"],dataset["report"]["raw_inventory"])["quota_warnings"]
    return result


def inspect_parser_json(directory,profile):
    files=inventory(directory,parser=True)
    records,warnings=parser_records(directory,files,profile)
    structures=[]
    for file in files:
        nodes=[]
        def visit(value,pointer=""):
            if len(nodes)>=200: return
            node={"pointer":pointer,"type":type(value).__name__}
            if isinstance(value,dict): node["keys"]=list(value)[:40]
            elif isinstance(value,list): node["length"]=len(value)
            else: node["sample"]=str(value)[:160]
            nodes.append(node)
            children=list(value.items())[:40] if isinstance(value,dict) else list(enumerate(value[:3])) if isinstance(value,list) else []
            for key,child in children: visit(child,pointer+"/"+str(key).replace("~","~0").replace("/","~1"))
        visit(json.loads((Path(directory)/file["path"]).read_text()))
        structures.append({"file":file["path"],"structure_sample":nodes,"sampling":"max 200 nodes, 40 dict keys and first 3 array items"})
    return {"files":files,"parser_hash":fingerprint(files),"mapped_records":records,"diagnostics":warnings,
            "structures":structures,
            "oracle_status":"candidate discovery only; never Gold"}


def inspect_entity(dataset,cid):
    entity=next((e for e in dataset["entities"] if e["id"]==cid),None)
    if entity is None: raise ValueError("unknown candidate entity")
    return {"entity":entity,"relations":[r for r in dataset["relations"] if cid in (r["source"],r["target"])],
            "cases":[c["case_id"] for c in dataset["cases"] if any(e["id"]==cid for e in c["gold_candidate"])]}


def inspect_relation(dataset,rid):
    edge=next((r for r in dataset["relations"] if r["id"]==rid),None)
    if edge is None: raise ValueError("unknown candidate relation")
    return {"relation":edge,"endpoints":[e for e in dataset["entities"] if e["id"] in (edge["source"],edge["target"])]}


def inspect_case(dataset,cid):
    case=next((c for c in dataset["cases"] if c["case_id"]==cid),None)
    if case is None: raise ValueError("unknown candidate case")
    return {"case":case,"sources":validate_case_sources(case,[r["path"] for r in dataset["report"]["raw_inventory"]])}


def case_sources(dataset,raw_dir):
    inspected=inspect_raw_structure(raw_dir)
    if inspected["corpus_hash"]!=dataset["report"]["raw_hash"]: raise ValueError("raw input fingerprint differs from generated dataset")
    return {"checks":[validate_case_sources(c,[f["path"] for f in inspected["files"]],inspected["units"]) for c in dataset["cases"]],
            "raw_diagnostics":inspected["diagnostics"]}
