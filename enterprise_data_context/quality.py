from .classification import validate_classification_sections


def validate_contexts(contexts):
    issues=[]
    paths={}
    ids={}
    aliases={}
    for c in contexts:
        if c.identity_status in {"INFERRED","CANDIDATE"}:
            issues.append({
                "severity":"warning","code":"candidate_context_not_indexed","context":c.path
            })
        if c.canonical_id in ids:
            issues.append({"severity":"error","code":"duplicate_canonical_id","canonical_id":c.canonical_id})
        ids[c.canonical_id]=c.path
        if c.path in paths:
            issues.append({"severity":"error","code":"duplicate_path","path":c.path})
        paths[c.path]=c.canonical_id
        for a in c.aliases:
            key=(c.context_type,a.lower())
            if key in aliases and aliases[key]!=c.canonical_id:
                issues.append({"severity":"warning","code":"alias_collision","alias":a})
            aliases[key]=c.canonical_id
        for r in c.references:
            if r.status=="CONFIRMED" and not r.target_path:
                issues.append({"severity":"error","code":"broken_confirmed_reference","context":c.path})
            if not 0.0 <= r.confidence <= 1.0:
                issues.append({"severity":"error","code":"invalid_reference_confidence","context":c.path})
        for sec,val in c.sections.items():
            if val not in (None,"",[],{}) and not c.evidence.get(sec) and sec not in {
                "primary_objects","related_objects","topic","topic_domain"
            }:
                issues.append({"severity":"warning","code":"missing_evidence","context":c.path,"section":sec})
        for sec, candidates in c.candidate_sections.items():
            for candidate in candidates:
                if candidate.get("status") not in {"INFERRED", "CANDIDATE"}:
                    issues.append({"severity":"error","code":"invalid_candidate_status","context":c.path,"section":sec})
                confidence=candidate.get("confidence",0.0)
                if not 0.0 <= confidence <= 1.0:
                    issues.append({"severity":"error","code":"invalid_candidate_confidence","context":c.path,"section":sec})
        if c.context_type in {"physical-model", "logical-model"}:
            for classification_issue in validate_classification_sections(c.sections):
                issues.append({"context": c.path, **classification_issue})

    known_paths=set(paths)
    for c in contexts:
        for r in c.references:
            if r.status=="CONFIRMED" and r.target_path not in known_paths:
                issues.append({
                    "severity":"error","code":"missing_reference_target",
                    "context":c.path,"target":r.target_path,
                })
    return issues
