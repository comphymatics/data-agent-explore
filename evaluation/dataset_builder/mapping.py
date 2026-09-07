"""JSON-pointer mappings and raw structural rules; all layout differences are injected."""
from fnmatch import fnmatch
import json
from pathlib import Path
import re


def select(value,pointer):
    if pointer=="": return [("",value)]
    if not isinstance(pointer,str) or not pointer.startswith("/"): raise ValueError("selectors use JSON pointers")
    rows=[("",value)]
    for part in pointer[1:].split("/"):
        key=part.replace("~1","/").replace("~0","~")
        next_rows=[]
        for prefix,item in rows:
            if key=="*":
                values=item.items() if isinstance(item,dict) else enumerate(item) if isinstance(item,list) else []
            elif isinstance(item,dict): values=[(key,item[key])] if key in item else []
            elif isinstance(item,list) and key.isdigit() and int(key)<len(item): values=[(key,item[int(key)])]
            else: values=[]
            next_rows.extend((prefix+"/"+str(k).replace("~","~0").replace("/","~1"),v) for k,v in values)
        rows=next_rows
    return rows


def mapped(record,mapping):
    result={}
    for name,spec in mapping.items():
        if isinstance(spec,dict) and set(spec)=={"literal"}: result[name]=spec["literal"]
        elif isinstance(spec,dict): result[name]=mapped(record,spec)
        else:
            values=select(record,spec)
            result[name]=values[0][1] if len(values)==1 else [v for _,v in values] if values else None
    return result


def parser_records(root,files,profile):
    output={"entities":[],"relations":[]}; warnings=[]
    for file in files:
        name=file["path"]
        # Path.match('**/*.json') excludes root files on some Python versions.
        if not (Path(name).match(profile.file_glob) or profile.file_glob=="**/*.json" and name.endswith(".json")):
            warnings.append({"file":name,"code":"profile_excluded_parser_file"}); continue
        document=json.loads((Path(root)/name).read_text())
        count=0
        for kind in output:
            for rule in getattr(profile,kind):
                for pointer,record in select(document,rule["records"]):
                    row=mapped(record,rule["mapping"])
                    row["parser_location"]={"parser_file":name,"pointer":pointer}
                    output[kind].append(row); count+=1
        if not count: warnings.append({"file":name,"code":"no_parser_profile_matches"})
    return output,warnings


def raw_records(units,profile):
    output={"entities":[],"relations":[]}; diagnostics=[]
    for kind in output:
        for index,rule in enumerate(getattr(profile,"raw_"+kind)):
            before=len(output[kind])
            pattern=re.compile(rule["pattern"]) if rule.get("pattern") else None
            for unit in units:
                if unit["kind"]!=rule["kind"] or not fnmatch(unit["document"],rule.get("file_glob","*")): continue
                if not fnmatch(unit["location"].get("sheet",""),rule.get("sheet_glob","*")): continue
                if any(unit["location"].get(key)!=value for key,value in rule.get("location_match",{}).items()): continue
                if unit["location"].get("row",1)<rule.get("start_row",1): continue
                record=unit["record"]
                if pattern:
                    match=pattern.search(unit["text"])
                    if not match: continue
                    record={**record,**match.groupdict()}
                row=mapped(record,rule["mapping"])
                row.update(source_documents=[unit["document"]],source_locations=[unit["location"]],
                           raw_rule=f"{kind}:{index}",unit_id=unit["unit_id"])
                output[kind].append(row)
            if len(output[kind])==before:
                diagnostics.append({"code":"raw_rule_no_matches","rule":f"{kind}:{index}"})
    if not profile.raw_entities and not profile.raw_relations:
        diagnostics.append({"code":"raw_independent_discovery_not_configured","meaning":"zero observed blind spots does not establish Parser completeness"})
    output["diagnostics"]=diagnostics
    return output
