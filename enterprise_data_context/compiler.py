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
from .classification import normalize_context_classification
from .organization import SemanticOrganizationBuilder

class ContextCompiler:
    def __init__(self,semantic_provider=None):
        self.rule=RuleExtractor()
        self.heuristic=HeuristicExtractor()
        self.semantic=SemanticExtractor(semantic_provider)
        self.mapper=BusinessSemanticMapper()
        self.materializer=PageMaterializer()
        self.organization=SemanticOrganizationBuilder()

    def compile(self,sources):
        """Compatibility entrypoint: parse registered sources, then compile downstream."""
        docs=[]
        for s in sources:
            doc=parse_document(s["id"],s["path"],s.get("type","unknown"))
            docs.append(doc)
        return self.compile_documents(docs, sources=sources)

    def compile_documents(self, documents, sources=None):
        """Compile parser-owned DocumentIR objects without reading raw files."""
        fragments=[]
        for doc in documents:
            fragments += self.rule.extract(doc)
            fragments += self.heuristic.extract(doc)
            fragments += self.semantic.extract(doc)
        return self.compile_fragments(fragments, documents=documents, sources=sources)

    def compile_template_inputs(self, path):
        """Compile the external parser's agreed Template JSON delivery."""
        from .template_input import load_template_inputs

        batch = load_template_inputs(path)
        compiled = self.compile_fragments(batch["fragments"], sources=batch["sources"])
        compiled["template_input_files"] = batch["files"]
        compiled["coverage_declaration"] = {
            "status": "PARTIAL",
            "scope": "template-input",
            "reason": "Template deliveries are partial unless an authoritative inventory declares completeness.",
        }
        return compiled

    def compile_fragments(self, fragments, documents=None, sources=None):
        """
        Compile normalized internal ContextFragment IR.

        External parser teams deliver the Template JSON contract consumed by
        ``compile_template_inputs``. This lower-level entrypoint remains the internal
        normalization boundary and a compatibility API for tests and existing callers.
        All governed downstream behavior starts here.
        """
        fragments=list(fragments)
        documents=list(documents or [])
        canonical=CanonicalResolver()
        merge=MergeEngine()

        grouped=defaultdict(list); contexts={}
        for f in fragments:
            c=canonical.resolve_or_create(f)
            contexts[c.canonical_id]=c
            grouped[c.canonical_id].append(f)
            merge.merge(c,f)

        for cid,fs in grouped.items():
            self.mapper.apply(contexts[cid],fs)
            normalize_context_classification(contexts[cid])

        rr=ReferenceResolver(canonical.registry)
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

        organization=self.organization.build(list(contexts.values()))
        hierarchy=organization["hierarchy"]
        pages=[
            self.materializer.materialize(c,hierarchy=hierarchy.describe(c.path))
            for c in contexts.values()
        ]
        pidx=PageIndex(); eidx=ElementIndex()
        for p in pages: pidx.add(p); eidx.add(p)
        graph=BackendGraph().project(list(contexts.values()))
        return {
            "documents":documents,"fragments":fragments,"contexts":list(contexts.values()),"pages":pages,
            "page_index":pidx,"element_index":eidx,"graph":graph,
            "hierarchy":hierarchy,
            "association_report":organization["association_report"],
            "backrefs":build_backrefs(list(contexts.values())),
            "quality_issues":validate_contexts(list(contexts.values())),
            "coverage_declaration": {
                "status": "UNKNOWN",
                "scope": "unspecified",
                "reason": "No authoritative source inventory declared completeness.",
            },
            "source_fingerprints":{
                s["id"]: s.get("fingerprint") for s in (sources or []) if s.get("id")
            },
        }
