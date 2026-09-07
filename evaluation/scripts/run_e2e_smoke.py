"""One real raw-to-Explore pipeline, six fixture cases, three repeats; no competitor simulation."""
import argparse
from pathlib import Path
import sys
import tempfile
from evaluation.fixtures.raw_smoke import create_raw
from evaluation.benchmark.e2e_runner import run


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",required=True)
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="e2e-smoke-input-") as temp:
        raw=create_raw(Path(temp)/"raw")
        result=run(corpus_path=raw,cases_path=root/"cases/cases.yaml",aliases_path=root/"cases/aliases.yaml",
            config={"model":{"model":"deterministic","version":"core","temperature":0,"max_output":2048,"native_model_constraint":True},
                    "hardware_class":"local-smoke","systems":{"data_explore":{"parser_version":"synthetic-table-parser/v1", "smoke_parser":True,
                    "parser_command":[sys.executable,"-m","evaluation.fixtures.smoke_parser"]}}},
            output=args.output,systems=["data_explore"],repeats=3,smoke=True)
        if result["statistics"]["data_explore"]["invalid_run_rate"]!=0:
            raise SystemExit("E2E smoke execution failed; inspect run_manifest.json")


if __name__=="__main__": main()
