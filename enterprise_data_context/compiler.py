from collections import defaultdict
from .ingestion.registry import parse_document
from .extraction.rule_extractor import RuleExtractor
from .extraction.heuristic_extractor import HeuristicExtractor
from .extraction.semantic import SemanticExtractor
from .canonical.resolver import CanonicalResolver
from .fusion.merge import MergeEngine
from .mapping.business import BusinessSemanticMapper
from .references.resolver import ReferenceResolver, build_backrefs
from .materialization.pages import PageMaterializer
from .indexes.page import PageIndex
from .indexes.element import ElementIndex
from .graph.backend import BackendGraph
from .quality import validate_contexts

class ContextCompiler:
    def __init__(self,semantic_provider=None):
        self.rule=RuleExtractor()
        self.heuristic=HeuristicExtractor()
        self.semantic=SemanticExtractor(semantic_provider)
        self.canonical=CanonicalResolver()
        self.merge=MergeEngine()
        self.mapper=BusinessSemanticMapper()
        self.materializer=PageMaterializer()

    def compile(self,sources):
        docs=[]; fragments=[]
        for s in sources:
            doc=parse_document(s["id"],s["path"],s.get("type","unknown"))
            docs.append(doc)
            fragments += self.rule.extract(doc)
            fragments += self.heuristic.extract(doc)
            fragments += self.semantic.extract(doc)

        grouped=defaultdict(list); contexts={}
        for f in fragments:
            c=self.canonical.resolve_or_create(f)
            contexts[c.canonical_id]=c
            grouped[c.canonical_id].append(f)
            self.merge.merge(c,f)

        for cid,fs in grouped.items():
            self.mapper.apply(contexts[cid],fs)

        rr=ReferenceResolver(self.canonical.registry)
        for c in contexts.values():
            rr.resolve_context(c)
            c.coverage={
                "business_meaning":bool(c.sections.get("summary")),
                "purpose":c.context_type=="analysis-purpose" or bool(c.sections.get("analysis_purposes")),
                "business_object":bool(c.sections.get("primary_objects") or c.context_type=="business-object"),
                "metrics":c.context_type=="metric" or bool(c.sections.get("metrics")),
                "dimensions":bool(c.sections.get("dimensions")),
                "models":c.context_type in ("physical-model","logical-model"),
                "fields":bool(c.sections.get("important_fields")),
                "grain":bool(c.sections.get("grain")),
                "lineage":bool(c.sections.get("lineage.upstream") or c.sections.get("lineage.downstream")),
            }

        pages=[self.materializer.materialize(c) for c in contexts.values()]
        pidx=PageIndex(); eidx=ElementIndex()
        for p in pages: pidx.add(p); eidx.add(p)
        graph=BackendGraph().project(list(contexts.values()))
        return {
            "documents":docs,"fragments":fragments,"contexts":list(contexts.values()),"pages":pages,
            "page_index":pidx,"element_index":eidx,"graph":graph,
            "backrefs":build_backrefs(list(contexts.values())),
            "quality_issues":validate_contexts(list(contexts.values()))
        }
