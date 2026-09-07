# LEGACY / NON-HEADLINE EVALUATION — official entry: python -m evaluation
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class RetrievalResult:
    system: str
    case_id: str
    query_id: str
    query: str
    repeat: int
    evidence_ids: list[str] = field(default_factory=list)
    query_tokens: int | None = None
    token_details: dict[str, Any] = field(default_factory=dict)
    latency_seconds: float = 0.0
    valid: bool = True
    error: str | None = None
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CaseScore:
    system: str
    case_id: str
    query_id: str
    repeat: int
    evidence_recall: float | None
    evidence_precision: float
    query_tokens: int | None
    token_complete: bool
    matched_required: list[str]
    matched_allowed: list[str]
    returned_forbidden: list[str]
    returned_unknown: list[str]
    valid: bool
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
