import argparse
import json
from pathlib import Path
from evaluation.benchmark.e2e_runner import run


def main():
    parser=argparse.ArgumentParser(description="Four complete E2E systems over frozen raw documents")
    parser.add_argument("command",nargs="?",choices=("run","preflight"),default="run")
    for name in ("corpus","cases","aliases","config","output"): parser.add_argument("--"+name,required=True)
    parser.add_argument("--systems",nargs="+")
    parser.add_argument("--repeats",type=int,default=3)
    parser.add_argument("--smoke",action="store_true")
    args=parser.parse_args()
    from evaluation.benchmark.result_contract import SYSTEMS
    if args.command=="preflight" and args.smoke:
        parser.error("formal preflight cannot use --smoke")
    try:
        result=run(corpus_path=args.corpus,cases_path=args.cases,aliases_path=args.aliases,
            config=json.loads(Path(args.config).read_text()),output=args.output,repeats=args.repeats,
            systems=args.systems or SYSTEMS,smoke=args.smoke,preflight_only=args.command=="preflight")
    except (ValueError,OSError) as exc:
        print(json.dumps({"status":"FAIL","error":str(exc),"output":args.output}))
        raise SystemExit(2)
    print(json.dumps({"headline_eligible":result["manifest"]["headline_eligible"],
                      "preflight":result["manifest"]["preflight"]["status"],"output":args.output}))
    if args.command=="run" and not args.smoke and not result["manifest"]["headline_eligible"]: raise SystemExit(2)


if __name__=="__main__": main()
