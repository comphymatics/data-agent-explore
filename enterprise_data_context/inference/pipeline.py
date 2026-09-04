from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
import json
import re
from typing import Any

from jsonschema import Draft202012Validator

from enterprise_data_context.classification import load_classification_catalog
from enterprise_data_context.models import ContextFragment, Evidence, SourceLocation, TypedReference

from .config import LLMInferenceConfig
from .provider import StructuredInferenceProvider


SCHEMA_VERSION = "1.0"
SOURCE_TYPES = {"scenario", "analysis-purpose"}
TARGET_RELATIONS = {
    "uses_metric": "metric",
    "analyzes_business_object": "business-object",
    "supported_by_logical_model": "logical-model",
    "supported_by_physical_model": "physical-model",
}
PROVIDER_OUTPUT_SCHEMA = {
    "type": "object",
    "required": ["relationships"],
    "properties": {
        "relationships": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["relation", "target_path", "confidence", "rationale", "evidence_paths"],
                "properties": {
                    "relation": {"enum": sorted(TARGET_RELATIONS)},
                    "target_path": {"type": "string", "minLength": 1},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "rationale": {"type": "string", "minLength": 1, "maxLength": 1000},
                    "evidence_paths": {
                        "type": "array", "minItems": 1, "uniqueItems": True,
                        "items": {"type": "string", "minLength": 1},
                    },
                },
                "additionalProperties": False,
            },
        }
    },
    "additionalProperties": False,
}

SYSTEM_PROMPT = """You propose governed semantic relationships for an enterprise data context.
Use only target_path values from candidate_targets and evidence_paths from evidence_catalog.
Never claim that a physical asset exists outside the supplied snapshot. Never invent a target.
Omit a relationship when evidence is insufficient. Return only one JSON object with this shape:
{"relationships":[{"relation":"uses_metric|analyzes_business_object|supported_by_logical_model|supported_by_physical_model","target_path":"data://...","confidence":0.0,"rationale":"short evidence-based explanation","evidence_paths":["data://..."]}]}
Every output is a CANDIDATE proposal and requires review; do not use confirmed/fact language."""


@dataclass
class InferenceRun:
    report: dict
    fragments: list[ContextFragment] = field(default_factory=list)

    def fragment_rows(self) -> list[dict]:
        return [asdict(fragment) for fragment in self.fragments]


class SemanticInferencePipeline:
    """Bounded offline LLM enrichment over Rich Pages, never raw graph traversal."""

    def __init__(self, config: LLMInferenceConfig, provider: StructuredInferenceProvider):
        config.validate()
        if not config.enabled:
            raise ValueError("LLM inference is disabled in config")
        self.config = config
        self.provider = provider
        self.output_validator = Draft202012Validator(PROVIDER_OUTPUT_SCHEMA)

    def run(self, compiled: dict, source_paths: list[str] | None = None) -> InferenceRun:
        pages = {page.path: page for page in compiled["pages"]}
        sources = self._source_pages(list(pages.values()), source_paths)
        base_version = compiled.get("index_version") or compiled.get("manifest", {}).get("index_version")
        created_at = datetime.now(timezone.utc).isoformat()
        proposals: list[dict[str, Any]] = []
        rejections: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []

        for source in sources:
            request_payload = self._request_payload(source, list(pages.values()), base_version)
            try:
                input_size = len(json.dumps(request_payload, ensure_ascii=False))
                if input_size > self.config.max_input_characters:
                    raise ValueError(
                        f"bounded Evidence Pack has {input_size} characters; "
                        f"limit is {self.config.max_input_characters}"
                    )
                raw = self.provider.infer(system_prompt=SYSTEM_PROMPT, payload=request_payload)
                validation_errors = sorted(
                    self.output_validator.iter_errors(raw), key=lambda error: list(error.path)
                )
                if validation_errors:
                    errors.append({
                        "source_path": source.path,
                        "code": "invalid_provider_output",
                        "message": validation_errors[0].message,
                    })
                    continue
                accepted, rejected = self._validate_relationships(source, raw, request_payload, pages)
                proposals.extend(accepted)
                rejections.extend(rejected)
            except Exception as exc:
                errors.append({
                    "source_path": source.path,
                    "code": "provider_error",
                    "message": f"{type(exc).__name__}: {exc}",
                })

        proposals = self._dedupe_proposals(proposals)
        seed = {
            "base_index_version": base_version,
            "provider": self.config.provider,
            "model": self.config.model,
            "prompt_version": self.config.prompt_version,
            "sources": [page.path for page in sources],
            "proposals": proposals,
        }
        run_hash = sha256(
            json.dumps(seed, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        run_id = f"semantic-inference-{run_hash[:16]}"
        for index, proposal in enumerate(proposals):
            proposal["proposal_id"] = f"{run_id}:{index:04d}"
            proposal["run_id"] = run_id

        report = {
            "schema_version": SCHEMA_VERSION,
            "run_id": run_id,
            "base_index_version": base_version,
            "created_at": created_at,
            "status": "FAILED" if errors and not proposals else ("PARTIAL" if errors or rejections else "SUCCEEDED"),
            "assertion_status": "CANDIDATE",
            "provider": {
                "kind": self.config.provider,
                "model": self.config.model,
                "prompt_version": self.config.prompt_version,
            },
            "policy": {
                "bounded_rich_page_input": True,
                "candidate_only": True,
                "requires_review": True,
                "candidate_limit_per_type": self.config.candidate_limit_per_type,
                "max_input_characters": self.config.max_input_characters,
                "minimum_confidence": self.config.minimum_confidence,
                "base_coverage_status": (
                    compiled.get("coverage_declaration", {}).get("status") or "UNKNOWN"
                ),
            },
            "source_count": len(sources),
            "proposal_count": len(proposals),
            "rejection_count": len(rejections),
            "error_count": len(errors),
            "proposals": proposals,
            "rejections": rejections,
            "errors": errors,
        }
        return InferenceRun(report=report, fragments=self._to_fragments(report, pages))

    def _source_pages(self, pages, source_paths):
        selected = [
            page for page in pages
            if page.context_type in SOURCE_TYPES
            and page.facets.get("semantic_role") in {"app-feature", "modeling-analysis"}
        ]
        if source_paths:
            wanted = set(source_paths)
            missing = wanted - {page.path for page in selected}
            if missing:
                raise ValueError(f"unknown or unsupported inference source paths: {', '.join(sorted(missing))}")
            selected = [page for page in selected if page.path in wanted]
        return sorted(selected, key=lambda page: page.path)[: self.config.max_sources]

    def _request_payload(self, source, pages, base_version):
        candidates = defaultdict(list)
        for target_type in TARGET_RELATIONS.values():
            ranked = sorted(
                (self._rank_target(source, page) for page in pages if page.context_type == target_type),
                key=lambda row: (-row["score"], row["path"]),
            )[: self.config.candidate_limit_per_type]
            candidates[target_type] = ranked
        evidence_catalog = [{
            "path": source.path,
            "context_type": source.context_type,
            "name": source.name,
            "summary": source.l0,
        }]
        for rows in candidates.values():
            evidence_catalog.extend({
                "path": row["path"], "context_type": row["context_type"],
                "name": row["name"], "summary": row["summary"],
            } for row in rows)
        unique_evidence = {row["path"]: row for row in evidence_catalog}
        return {
            "base_index_version": base_version,
            "prompt_version": self.config.prompt_version,
            "source_page": self._compact_page(source),
            "existing_references": list(source.references),
            "candidate_targets": dict(candidates),
            "evidence_catalog": list(unique_evidence.values()),
            "modeling_standard": self._compact_standard(),
            "allowed_relations": TARGET_RELATIONS,
        }

    def _rank_target(self, source, target):
        source_text = self._page_text(source)
        target_text = self._page_text(target)
        source_terms = _terms(source_text)
        target_terms = _terms(target_text)
        overlap = source_terms & target_terms
        score = min(0.6, len(overlap) * 0.06)
        reasons = []
        if overlap:
            reasons.append("term_overlap:" + ",".join(sorted(overlap)[:6]))
        explicit_names = {
            str(value).casefold()
            for key in ("metrics", "primary_objects", "related_objects")
            for value in _as_list(source.l2.get(key))
        }
        if target.name.casefold() in explicit_names:
            score += 0.35
            reasons.append("explicit_source_list")
        for facet in ("topic_domain", "topic", "application"):
            left = source.l2.get(facet) or source.facets.get(facet)
            right = target.l2.get(facet) or target.facets.get(facet)
            if left and right and str(left).casefold() == str(right).casefold():
                score += 0.15
                reasons.append(f"same_{facet}")
        return {
            "path": target.path,
            "context_type": target.context_type,
            "name": target.name,
            "summary": target.l0,
            "facets": target.facets,
            "score": round(min(score, 1.0), 4),
            "reasons": reasons,
        }

    def _validate_relationships(self, source, raw, request_payload, pages):
        allowed_targets = {
            row["path"]
            for rows in request_payload["candidate_targets"].values()
            for row in rows
        }
        allowed_evidence = {row["path"] for row in request_payload["evidence_catalog"]}
        already_confirmed = {
            (reference.get("relation"), reference.get("target_path"))
            for reference in source.references
            if reference.get("status") == "CONFIRMED" and reference.get("target_path")
        }
        accepted = []
        rejected = []
        for row in raw["relationships"]:
            reason = None
            target = pages.get(row["target_path"])
            if row["target_path"] not in allowed_targets or target is None:
                reason = "target_not_in_bounded_candidates"
            elif TARGET_RELATIONS[row["relation"]] != target.context_type:
                reason = "relation_target_type_mismatch"
            elif not set(row["evidence_paths"]).issubset(allowed_evidence):
                reason = "evidence_outside_bounded_catalog"
            elif source.path not in row["evidence_paths"]:
                reason = "source_page_evidence_required"
            elif target.path not in row["evidence_paths"]:
                reason = "target_page_evidence_required"
            elif (row["relation"], target.path) in already_confirmed:
                reason = "relationship_already_confirmed"
            elif float(row["confidence"]) < self.config.minimum_confidence:
                reason = "below_minimum_confidence"
            if reason:
                rejected.append({
                    "source_path": source.path,
                    "target_path": row.get("target_path"),
                    "relation": row.get("relation"),
                    "reason": reason,
                })
                continue
            accepted.append({
                "source_path": source.path,
                "source_name": source.name,
                "relation": row["relation"],
                "target_path": target.path,
                "target_name": target.name,
                "target_type": target.context_type,
                "confidence": float(row["confidence"]),
                "rationale": row["rationale"],
                "evidence_paths": list(row["evidence_paths"]),
                "status": "CANDIDATE",
            })
        return accepted, rejected

    @staticmethod
    def _dedupe_proposals(proposals):
        out = []
        seen = set()
        for proposal in proposals:
            key = (proposal["source_path"], proposal["relation"], proposal["target_path"])
            if key not in seen:
                seen.add(key)
                out.append(proposal)
        return out

    def _to_fragments(self, report, pages):
        fragments = []
        for proposal in report["proposals"]:
            source = pages[proposal["source_path"]]
            evidence = [Evidence(
                SourceLocation(
                    source_id=f"context-snapshot:{report['base_index_version'] or 'unversioned'}",
                    path=path,
                    section="Rich Context Page",
                ),
                note=f"LLM candidate input; {proposal['proposal_id']}",
            ) for path in proposal["evidence_paths"]]
            evidence.append(Evidence(
                SourceLocation(
                    source_id=f"llm-inference:{report['run_id']}",
                    path=f"inference://runs/{report['run_id']}",
                    section=proposal["proposal_id"],
                ),
                note=(
                    f"provider={report['provider']['kind']}; model={report['provider']['model']}; "
                    f"prompt={report['provider']['prompt_version']}"
                ),
            ))
            reference = TypedReference(
                relation=proposal["relation"],
                raw_target=proposal["target_name"],
                target_type=proposal["target_type"],
                status="CANDIDATE",
                target_path=proposal["target_path"],
                confidence=proposal["confidence"],
                evidence=list(evidence),
            )
            fragments.append(ContextFragment(
                fragment_id=proposal["proposal_id"],
                context_type=source.context_type,
                candidate_name=source.name,
                section_type="references",
                payload={
                    "proposal_id": proposal["proposal_id"],
                    "rationale": proposal["rationale"],
                },
                aliases=list(source.aliases),
                references=[reference],
                evidence=evidence,
                source_type="llm_semantic_inference",
                confidence=proposal["confidence"],
                status="CANDIDATE",
            ))
        return fragments

    @staticmethod
    def _compact_page(page):
        return {
            "path": page.path,
            "context_type": page.context_type,
            "name": page.name,
            "aliases": page.aliases,
            "facets": page.facets,
            "summary": page.l0,
            "sections": {
                key: _bounded_value(page.l2[key])
                for key in (
                    "scenario.kind", "application", "topic_domain", "topic", "metrics",
                    "primary_objects", "related_objects", "analysis_purposes",
                )
                if page.l2.get(key) not in (None, "", [], {})
            },
        }

    @staticmethod
    def _compact_standard():
        catalog = load_classification_catalog()
        return {
            "catalog_version": catalog["catalog_version"],
            "layers": {
                code: {"name": row["name"], "domain_policy": row["domain_policy"]}
                for code, row in catalog["layers"].items()
            },
            "domains": {
                layer: {
                    name: {"code": row.get("code"), "topics": row.get("topics", [])}
                    for name, row in domains.items()
                }
                for layer, domains in catalog.get("domains", {}).items()
            },
        }

    @classmethod
    def _page_text(cls, page):
        compact = cls._compact_page(page)
        return json.dumps(compact, ensure_ascii=False, sort_keys=True)


def _as_list(value):
    if value in (None, ""):
        return []
    return value if isinstance(value, list) else [value]


def _terms(value):
    text = str(value or "").casefold()
    latin = set(re.findall(r"[a-z0-9]{2,}", text))
    cjk_runs = re.findall(r"[\u3400-\u9fff]{2,}", text)
    cjk = {
        run[index:index + 2]
        for run in cjk_runs
        for index in range(len(run) - 1)
    }
    return latin | cjk


def _bounded_value(value, *, list_limit=60, string_limit=2000):
    if isinstance(value, str):
        return value[:string_limit]
    if isinstance(value, list):
        return [_bounded_value(item) for item in value[:list_limit]]
    if isinstance(value, dict):
        return {str(key): _bounded_value(item) for key, item in list(value.items())[:list_limit]}
    return value
