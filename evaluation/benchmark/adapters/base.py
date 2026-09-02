from __future__ import annotations

import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from ..models import RetrievalResult


MARKED_EVIDENCE_RE = re.compile(r"EVIDENCE_ID\s*:\s*`?(ev-[a-z0-9][a-z0-9._-]*)`?", re.IGNORECASE)
GENERAL_EVIDENCE_RE = re.compile(r"\bev-[a-z0-9][a-z0-9._-]*", re.IGNORECASE)


def extract_evidence_ids(text: str) -> list[str]:
    marked = MARKED_EVIDENCE_RE.findall(text)
    values = marked or GENERAL_EVIDENCE_RE.findall(text)
    cleaned: list[str] = []
    for value in values:
        normalized = value.rstrip(".,;:)]}`\"'")
        if normalized.endswith(".md"):
            normalized = normalized[:-3]
        cleaned.append(normalized.lower())
    return list(dict.fromkeys(cleaned))


class RetrievalAdapter(ABC):
    name: str

    def __init__(self, config: dict[str, Any], corpus_dir: Path):
        self.config = config
        self.corpus_dir = corpus_dir.resolve()

    @abstractmethod
    def preflight(self) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def retrieve(
        self,
        case: dict[str, Any],
        query: str,
        query_id: str,
        repeat: int,
    ) -> RetrievalResult:
        raise NotImplementedError
