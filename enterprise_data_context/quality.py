def validate_contexts(contexts):
    issues=[]
    paths={}
    aliases={}
    for c in contexts:
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
        for sec,val in c.sections.items():
            if val not in (None,"",[],{}) and not c.evidence.get(sec) and sec not in {
                "primary_objects","related_objects","topic","topic_domain"
            }:
                issues.append({"severity":"warning","code":"missing_evidence","context":c.path,"section":sec})
    return issues
