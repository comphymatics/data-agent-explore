"""Stable candidate contracts and injectable profiles. No production contract changes."""
from dataclasses import asdict, dataclass, field
import hashlib
import json
from pathlib import Path
from typing import Protocol
import yaml
from evaluation.benchmark.result_contract import ENTITY_TYPES, RELATION_TYPES

VERSION = "dataset-builder/v1"
ORIGINS = {"parser", "raw_independent", "both"}
PREFIXES = dict(zip(ENTITY_TYPES, ("scenario", "purpose", "metric", "dimension", "business-object",
                                  "logical-model", "physical-model", "field")))
# has_field is builder-only structural ownership, never a public Pilot relation.
BUILDER_RELATIONS = {*RELATION_TYPES, "has_field"}


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass
class ParserProfile:
    file_glob: str = "**/*.json"
    entities: list = field(default_factory=lambda: [{"records": "/entities/*", "mapping": {
        k: "/"+k for k in ("id", "type", "name", "aliases", "source_documents", "source_locations", "facets")}}])
    relations: list = field(default_factory=lambda: [{"records": "/relations/*", "mapping": {
        k: "/"+k for k in ("source", "target", "relation", "source_documents", "source_locations")}}])


@dataclass
class SourceProfile:
    document_aliases: dict = field(default_factory=dict)
    # Rules match structural units; names/columns/semantic rules belong in configuration.
    raw_entities: list = field(default_factory=list)
    raw_relations: list = field(default_factory=list)


@dataclass
class EntityMappingProfile:
    type_map: dict = field(default_factory=dict)
    identity_namespace: str = ""


@dataclass
class RelationMappingProfile:
    type_map: dict = field(default_factory=dict)


@dataclass
class DatasetGenerationProfile:
    target_count: int = 60
    max_cases_per_entity: int = 8
    max_cases_per_document: int = 20
    max_cases_per_topic: int = 15
    max_cases_per_motif: int = 4
    negative_candidates: list = field(default_factory=list)
    query_templates: dict = field(default_factory=dict)


@dataclass
class Profiles:
    parser: ParserProfile = field(default_factory=ParserProfile)
    source: SourceProfile = field(default_factory=SourceProfile)
    entity_mapping: EntityMappingProfile = field(default_factory=EntityMappingProfile)
    relation_mapping: RelationMappingProfile = field(default_factory=RelationMappingProfile)
    generation: DatasetGenerationProfile = field(default_factory=DatasetGenerationProfile)


def load_profiles(path=None):
    value=yaml.safe_load(Path(path).read_text()) if path else {}
    value=value or {}
    classes={"parser":ParserProfile,"source":SourceProfile,"entity_mapping":EntityMappingProfile,
             "relation_mapping":RelationMappingProfile,"generation":DatasetGenerationProfile}
    if not isinstance(value,dict) or set(value)-set(classes): raise ValueError("unknown Profile section")
    result=Profiles(**{key:cls(**value.get(key,{})) for key,cls in classes.items()})
    for key in ("target_count","max_cases_per_entity","max_cases_per_document","max_cases_per_topic","max_cases_per_motif"):
        number=getattr(result.generation,key)
        if not isinstance(number,int) or isinstance(number,bool) or number<1:
            raise ValueError("generation limits must be positive integers")
    return result


class RawReader(Protocol):
    def __call__(self, root: Path, inventory: list) -> tuple[list, list]:
        """Return structural units and diagnostics; never silently omit unsupported files."""
        ...


class QueryParaphraser(Protocol):
    def __call__(self, query: str) -> str:
        """Query-only input/output; no access to candidate Gold or Registry."""
        ...


def provenance(origin, documents, locations, method, raw_verified=False):
    return {"candidate_origin":origin,"source_documents":sorted(set(documents)),
            "source_locations":locations,"generation_method":[method],"parser_supported":origin in {"parser","both"},
            "raw_verified":raw_verified,"review_status":"DRAFT"}


def assert_draft(value):
    """Reject promoted artifacts anywhere; Builder has no approval path."""
    if isinstance(value,dict):
        if "review_status" in value and value["review_status"]!="DRAFT":
            raise ValueError("Dataset Builder only accepts/emits DRAFT review_status")
        if "gold" in value: raise ValueError("Builder artifacts contain gold_candidate, never approved gold")
        for child in value.values(): assert_draft(child)
    elif isinstance(value,list):
        for child in value: assert_draft(child)
