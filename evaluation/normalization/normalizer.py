from dataclasses import dataclass, field
import json
import re
from evaluation.benchmark.result_contract import ENTITY_TYPES
from .entity_registry import normalized

TYPE_ALIASES={"scenario":"scenarios","analysis_purpose":"purposes","analysis-purpose":"purposes",
    "purpose":"purposes","metric":"metrics","dimension":"dimensions","business-object":"business_objects",
    "business_object":"business_objects","logical-model":"logical_models","physical-model":"physical_models","field":"fields"}


@dataclass
class NormalizedExploreResult:
    entities: dict = field(default_factory=lambda:{k:set() for k in ENTITY_TYPES})
    unknown: set = field(default_factory=set)
    mentions: list = field(default_factory=list)
    relations: set = field(default_factory=set)
    unknown_relations: set = field(default_factory=set)

    def to_dict(self):
        return {"entities":{k:sorted(v) for k,v in self.entities.items()},"unknown":sorted(self.unknown),"mentions":self.mentions,
                "relations":[list(r) for r in sorted(self.relations)], "unknown_relations":sorted(self.unknown_relations)}


def normalize(output, registry):
    """The identical extraction/alias rules apply to every system. Never inspect trace."""
    result=NormalizedExploreResult()
    def add(value,typ=None):
        typ=TYPE_ALIASES.get(typ,typ)
        cid=registry.resolve(value,typ)
        if cid:
            result.entities[registry.entities[cid]["type"]].add(cid)
        else:
            result.unknown.add((typ or "untyped")+":"+normalized(value))
        result.mentions.append({"value":str(value),"type":typ,"canonical_id":cid})
    def visit(value,typ=None,parent=None):
        if isinstance(value,list):
            for item in value: visit(item,typ,parent)
        elif isinstance(value,dict):
            if typ=="fields" and (value.get("column_name") or value.get("field_name")):
                name=value.get("column_name") or value["field_name"]
                add(parent+"."+name if parent else name,"fields"); return
            entity_type=value.get("type") or value.get("context_type") or typ
            if "canonical_id" in value or ("name" in value and entity_type):
                key=value.get("canonical_id") or value["name"]
                if not registry.resolve(key,TYPE_ALIASES.get(entity_type,entity_type)) and value.get("name"):
                    key=value["name"]
                add(key,entity_type)
                return
            for key,item in value.items():
                mapped=TYPE_ALIASES.get(key,key)
                if mapped in ENTITY_TYPES: visit(item,mapped,parent)
                elif key in {"entities","primary_contexts","results","answer"}: visit(item)
                elif key=="focused_expansion" and isinstance(item,dict):
                    # Parent names come from returned contexts, not the hidden registry.
                    parents={r.get("path"):r.get("name") for r in value.get("primary_contexts",[]) if isinstance(r,dict)}
                    for path,expanded in item.items(): visit(expanded,parent=parents.get(path))
        elif isinstance(value,str):
            if typ:
                add(parent+"."+value if typ=="fields" and parent else value,typ); return
            try:
                parsed=json.loads(value)
            except (ValueError,TypeError):
                parsed=None
            if isinstance(parsed,(dict,list)):
                visit(parsed); return
            # Native prose must enumerate entities; unknown lines remain precision penalties.
            # We deliberately do not search known aliases in arbitrary prose: doing so hides
            # hallucinated names while rewarding only recognizable Gold vocabulary.
            for line in value.splitlines():
                line=re.sub(r"^\s*(?:[-*]|\d+[.)])\s*","",line).strip()
                if line: add(line)
    visit(output)
    if isinstance(output,dict):
        for edge in output.get("relations",[]):
            source=edge.get("source",{}); target=edge.get("target",{})
            source_id=registry.resolve(source.get("name"),source.get("type"))
            target_id=registry.resolve(target.get("name"),target.get("type"))
            if source_id and target_id:
                result.relations.add((source_id,edge["relation"],target_id))
            else:
                result.unknown_relations.add(json.dumps(edge,sort_keys=True,ensure_ascii=False))
    if isinstance(output,dict) and output and not result.mentions and not any(k in output for k in [*ENTITY_TYPES,"entities","primary_contexts","results","answer"]):
        result.unknown.add("unrecognized-output:"+json.dumps(output,sort_keys=True))
    return result
