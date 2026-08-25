from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Any, Literal

ContextType = Literal[
    "scenario", "topic", "analysis-purpose", "business-object",
    "metric", "dimension", "logical-model", "physical-model", "unknown"
]
RefStatus = Literal["CONFIRMED", "CANDIDATE", "UNRESOLVED"]

@dataclass
class SourceLocation:
    source_id: str
    path: str
    sheet: str | None = None
    section: str | None = None
    table: str | None = None
    row: int | None = None
    column: int | None = None
    cell: str | None = None

@dataclass
class DocumentElement:
    type: str
    id: str
    text: str | None = None
    title: str | None = None
    level: int | None = None
    headers: list[str] = field(default_factory=list)
    rows: list[list[Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    source: SourceLocation | None = None

@dataclass
class DocumentIR:
    source_id: str
    path: str
    source_type: str
    metadata: dict[str, Any] = field(default_factory=dict)
    elements: list[DocumentElement] = field(default_factory=list)

@dataclass
class Evidence:
    source: SourceLocation
    note: str | None = None

@dataclass
class TypedReference:
    relation: str
    raw_target: str
    target_type: str | None = None
    status: RefStatus = "UNRESOLVED"
    target_path: str | None = None
    confidence: float = 0.0
    evidence: list[Evidence] = field(default_factory=list)

@dataclass
class ContextFragment:
    fragment_id: str
    context_type: ContextType
    candidate_name: str
    section_type: str
    payload: Any
    aliases: list[str] = field(default_factory=list)
    identity_hints: dict[str, str] = field(default_factory=dict)
    features: dict[str, Any] = field(default_factory=dict)
    references: list[TypedReference] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)
    source_type: str = "unknown"
    confidence: float = 1.0

@dataclass
class CanonicalContext:
    canonical_id: str
    context_type: ContextType
    name: str
    path: str
    aliases: list[str] = field(default_factory=list)
    sections: dict[str, Any] = field(default_factory=dict)
    references: list[TypedReference] = field(default_factory=list)
    evidence: dict[str, list[Evidence]] = field(default_factory=dict)
    conflicts: list[dict[str, Any]] = field(default_factory=list)
    coverage: dict[str, bool] = field(default_factory=dict)
    environment_binding: dict[str, Any] = field(default_factory=lambda: {
        "canonical_role": None,
        "status": "unresolved",
        "matched_assets": []
    })

@dataclass
class ContextPage:
    canonical_id: str
    path: str
    context_type: ContextType
    name: str
    aliases: list[str]
    facets: dict[str, Any]
    l0: str
    l1: str
    l2: dict[str, Any]
    references: list[dict[str, Any]]
    coverage: dict[str, bool]
    environment_binding: dict[str, Any]

@dataclass
class SearchHit:
    path: str
    context_type: str
    name: str
    score: float
    reasons: list[str]
    l0: str
    l1: str

@dataclass
class ContextBundle:
    query: dict[str, Any]
    summary: str
    primary_contexts: list[dict[str, Any]]
    analysis_context: dict[str, Any]
    data_context: dict[str, Any]
    business_mapping: dict[str, Any]
    constraints: list[Any]
    environment: dict[str, Any]
    coverage: dict[str, bool]
    missing_context: list[str]
    sources: list[dict[str, Any]]
    confidence: float

def dump(obj):
    return asdict(obj)
