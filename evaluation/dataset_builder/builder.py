"""End-to-end, read-only source consumption and DRAFT-only artifact publication."""
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import yaml
from .contracts import VERSION, Profiles, fingerprint, assert_draft
from .source_inventory import inventory, read_raw
from .mapping import parser_records, raw_records
from .entity_graph import EntityGraph
from .alias_builder import build_aliases
from .raw_verifier import verify_entities, compare_raw_vs_parser
from .candidate_generator import generate_candidates
from .sampler import sample
from .quality import describe, validate_dataset
from .review_export import write_review


def build(raw_dir,parser_json_dir,out,profiles=None,raw_reader=read_raw,parser_reader=parser_records,paraphraser=None):
    profiles=profiles or Profiles()
    raw=Path(raw_dir).resolve(); parser=Path(parser_json_dir).resolve(); out=Path(out).resolve()
    if raw==parser or raw in parser.parents or parser in raw.parents:
        raise ValueError("raw and parser JSON inputs must be separate directories")
    if any(out==root or root in out.parents or out in root.parents for root in (raw,parser)):
        raise ValueError("scorer output must be outside raw/parser inputs and their ancestors")
    if out.exists() and any(out.iterdir()): raise ValueError("output must be empty")
    raw_files=inventory(raw); parser_files=inventory(parser,parser=True)
    units,raw_diagnostics=raw_reader(raw,raw_files)
    parsed,parser_diagnostics=parser_reader(parser,parser_files,profiles.parser)
    independent=raw_records(units,profiles.source)
    graph=EntityGraph(profiles,[r["path"] for r in raw_files])
    for source,origin in ((parsed,"parser"),(independent,"raw_independent")):
        graph.add_entities(source["entities"],origin)
    for source,origin in ((parsed,"parser"),(independent,"raw_independent")):
        graph.add_relations(source["relations"],origin)
    verify_entities(graph,units)
    entities=list(graph.entities.values()); relations=list(graph.relations.values())
    aliases=build_aliases(entities)
    for collision in aliases["collisions"]:
        for cid in collision["entity_ids"]: graph.entities[cid]["alias_collision"]=True
    candidates,generation=generate_candidates(graph,profiles.generation,paraphraser)
    selected,sampling=sample(candidates,profiles.generation)
    validation=validate_dataset(selected,entities,relations,aliases,raw_files)
    source_map={r["path"]:{"source":r,"entity_ids":[e["id"] for e in entities if r["path"] in e["source_documents"]],
                          "relation_ids":[e["id"] for e in relations if r["path"] in e["source_documents"]],
                          "raw_unit_ids":[u["unit_id"] for u in units if u["document"]==r["path"]]} for r in raw_files}
    report={"version":VERSION,"timestamp":datetime.now(timezone.utc).isoformat(),"review_status":"DRAFT",
            "raw_inventory":raw_files,"raw_hash":fingerprint(raw_files),"parser_inventory":parser_files,
            "parser_hash":fingerprint(parser_files),"profiles":asdict(profiles),"profile_hash":fingerprint(asdict(profiles)),
            "all_candidates":describe(candidates,entities,relations,aliases,raw_files),
            "selected":describe(selected,entities,relations,aliases,raw_files),
            "raw_vs_parser":compare_raw_vs_parser(graph),"generation":generation,"sampling":sampling,
            "raw_independent_discovery":{"configured":bool(profiles.source.raw_entities or profiles.source.raw_relations),
                "coverage":"PARTIAL_PROFILE_RULES","entity_records":len(independent["entities"]),"relation_records":len(independent["relations"]),
                "meaning":"unmatched raw information may remain; no completeness or absence assertion"},
            "diagnostics":[*raw_diagnostics,*parser_diagnostics,*independent["diagnostics"],*graph.warnings],"validation":validation}
    artifacts={"cases.draft.yaml":{"version":VERSION,"cases":selected},"aliases.draft.yaml":aliases,
               "candidate_entities.json":entities,"candidate_relations.json":relations,
               "source_entity_map.json":source_map,"generation_report.json":report}
    assert_draft(artifacts)
    if inventory(raw)!=raw_files or inventory(parser,True)!=parser_files: raise ValueError("source inputs changed during construction")
    out.mkdir(parents=True,exist_ok=True)
    for filename,value in artifacts.items():
        text=yaml.safe_dump(value,allow_unicode=True,sort_keys=False) if filename.endswith(".yaml") else json.dumps(value,ensure_ascii=False,indent=2)
        (out/filename).write_text(text)
    write_review(out,selected,entities,relations,aliases)
    return report
