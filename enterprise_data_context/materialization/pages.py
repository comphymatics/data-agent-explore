from enterprise_data_context.models import ContextPage

ORDER = [
    ("semantic_role","Semantic Role"),("scenario.kind","Scenario Kind"),
    ("scenario.parent_name","Parent Scenario Group"),("application","Application"),
    ("classification.layer","Layer"),("topic_domain","Topic Domain"),("topic","Topic"),
    ("primary_objects","Primary Business Objects"),("related_objects","Related Business Objects"),
    ("grain","Grain"),("dimensions","Dimensions"),("metrics","Metrics"),
    ("analysis_purposes","Analysis Purposes"),
    ("formula","Formula"),("customer_value","Customer Value"),
    ("measurement_point","Measurement Point"),("interfaces","Interfaces"),
    ("probes","Probes"),("semantic_reference.sid_domain","SID Domain"),
    ("semantic_reference.sid_abe","SID ABE"),("constraints","Constraints")
]

def fmt(v):
    if isinstance(v,list): return "\n".join(f"- {x}" for x in v)
    if isinstance(v,dict): return "\n".join(f"- {k}: {val}" for k,val in v.items())
    return str(v)

class PageMaterializer:
    def materialize(self, ctx, hierarchy=None):
        hierarchy=hierarchy or {}
        summary = ctx.sections.get("summary") or f"{ctx.name} ({ctx.context_type})"
        l0 = str(summary)[:700]
        lines=[f"# {ctx.name}","",str(summary)]
        for key,title in ORDER:
            v=ctx.sections.get(key)
            if v not in (None,"",[],{}):
                lines += ["",f"## {title}",fmt(v)]
        confirmed=[r for r in ctx.references if r.status=="CONFIRMED" and r.target_path]
        if confirmed:
            lines += ["","## References"] + [f"- {r.relation}: {r.target_path}" for r in confirmed]
        breadcrumb=hierarchy.get("breadcrumb",[])
        if len(breadcrumb)>1:
            lines += ["","## Hierarchy", " > ".join(row["name"] for row in breadcrumb)]
        facet_sections={
            "layer":"classification.layer", "topic_domain":"topic_domain", "topic":"topic",
            "grain":"grain", "primary_objects":"primary_objects",
            "sid_domain":"semantic_reference.sid_domain",
            "semantic_role":"semantic_role", "scenario_kind":"scenario.kind",
            "application":"application",
        }
        facets={facet:ctx.sections.get(section) for facet,section in facet_sections.items() if ctx.sections.get(section)}
        return ContextPage(
            canonical_id=ctx.canonical_id,
            path=ctx.path,
            context_type=ctx.context_type,
            name=ctx.name,
            aliases=list(ctx.aliases),
            facets=facets,
            l0=l0,
            l1="\n".join(lines),
            l2=dict(ctx.sections),
            references=[
                {
                    "relation":r.relation,
                    "raw_target":r.raw_target,
                    "target_path":r.target_path,
                    "status":r.status,
                    "confidence":r.confidence,
                }
                for r in ctx.references
            ],
            coverage=dict(ctx.coverage),
            environment_binding=dict(ctx.environment_binding),
            identity_status=ctx.identity_status,
            section_status=dict(ctx.section_status),
            candidates={k:list(v) for k,v in ctx.candidate_sections.items()},
            conflicts=list(ctx.conflicts),
            hierarchy=hierarchy,
        )
