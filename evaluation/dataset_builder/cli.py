"""Scorer-side Dataset Builder and internal read-only diagnostics."""
import argparse
import json
from pathlib import Path
from .contracts import load_profiles,fingerprint
from .builder import build
from .source_inventory import inventory, inspect_raw_structure
from .diagnostics import (load_dataset,validate,inspect_parser_json,inspect_entity,inspect_relation,inspect_case,case_sources)
from .quality import describe


def main(argv=None):
    parser=argparse.ArgumentParser(description="DRAFT-only Dataset Builder; no approval command")
    sub=parser.add_subparsers(dest="command",required=True)
    for name in ("inventory","inspect_raw_structure"):
        cmd=sub.add_parser(name); cmd.add_argument("--raw-dir",required=True)
    cmd=sub.add_parser("build")
    for key in ("raw-dir","parser-json-dir","out"): cmd.add_argument("--"+key,required=True)
    cmd.add_argument("--profile")
    cmd=sub.add_parser("inspect_parser_json"); cmd.add_argument("--parser-json-dir",required=True); cmd.add_argument("--profile")
    for name in ("validate","report","compare_raw_vs_parser","inspect_entity","inspect_relation","inspect_case","validate_case_sources"):
        cmd=sub.add_parser(name); cmd.add_argument("--dataset-dir",required=True)
        if name in {"inspect_entity","inspect_relation","inspect_case"}: cmd.add_argument("--id",required=True)
        if name=="validate_case_sources": cmd.add_argument("--raw-dir",required=True)
    args=parser.parse_args(argv)
    try:
        name=args.command
        if name=="inventory":
            files=inventory(args.raw_dir); result={"files":files,"corpus_hash":fingerprint(files)}
        elif name=="inspect_raw_structure": result=inspect_raw_structure(args.raw_dir)
        elif name=="inspect_parser_json": result=inspect_parser_json(args.parser_json_dir,load_profiles(args.profile).parser)
        elif name=="build": result=build(args.raw_dir,args.parser_json_dir,args.out,load_profiles(args.profile))
        elif name=="validate": result=validate(args.dataset_dir)
        else:
            dataset=load_dataset(args.dataset_dir)
            if name=="report": result=describe(dataset["cases"],dataset["entities"],dataset["relations"],dataset["aliases"],dataset["report"]["raw_inventory"])
            elif name=="compare_raw_vs_parser": result=dataset["report"]["raw_vs_parser"]
            elif name=="validate_case_sources": result=case_sources(dataset,args.raw_dir)
            else: result={"inspect_entity":inspect_entity,"inspect_relation":inspect_relation,"inspect_case":inspect_case}[name](dataset,args.id)
        print(json.dumps(result,ensure_ascii=False,indent=2))
        if args.command=="validate" and not result["source_valid"]: return 2
        if args.command=="validate_case_sources" and any(not c["valid"] for c in result["checks"]): return 2
        return 0
    except (ValueError,TypeError,OSError,KeyError) as exc:
        print(json.dumps({"status":"FAIL","error":str(exc)},ensure_ascii=False)); return 2


if __name__=="__main__": raise SystemExit(main())
