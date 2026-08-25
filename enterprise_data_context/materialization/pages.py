from enterprise_data_context.models import ContextPage

ORDER = [
    ("classification.layer","Layer"),("topic_domain","Topic Domain"),("topic","Topic"),
    ("primary_objects","Primary Business Objects"),("related_objects","Related Business Objects"),
    ("grain","Grain"),("dimensions","Dimensions"),("metrics","Metrics"),
    ("analysis_purposes","Analysis Purposes"),("important_fields","Important Fields"),
    ("formula","Formula"),("constraints","Constraints")
]

def fmt(v):
    if isinstance(v,list): return "\n".join(f"- {x}" for x in v)
    if isinstance(v,dict): return "\n".join(f"- {k}: {val}" for k,val in v.items())
    return str(v)

class PageMaterializer:
    def materialize(self, ctx):
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
        facets={k:ctx.sections.get(k) for k in ("classification.layer","topic_domain","topic","grain","primary_objects") if ctx.sections.get(k)}
        return ContextPage(
            ctx.canonical_id,ctx.path,ctx.context_type,ctx.name,ctx.aliases,facets,
            l0,"\n".join(lines),dict(ctx.sections),
            [{"relation":r.relation,"raw_target":r.raw_target,"target_path":r.target_path,
              "status":r.status,"confidence":r.confidence} for r in ctx.references],
            dict(ctx.coverage),dict(ctx.environment_binding)
        )
