# LEGACY / NON-HEADLINE EVALUATION — official entry: python -m evaluation
from __future__ import annotations

import re
from typing import Any


CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
NON_CJK_RE = re.compile(r"[^\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]+")


def estimate_tokens(text: str) -> int:
    """Deterministic fallback estimate when a system exposes no tokenizer usage.

    Chinese characters count as one token; remaining text uses four characters
    per token. Reports label this estimate so it is never confused with provider
    usage.
    """

    if not text:
        return 0
    cjk = len(CJK_RE.findall(text))
    non_cjk_chars = sum(len(match) for match in NON_CJK_RE.findall(text))
    return cjk + (non_cjk_chars + 3) // 4


def recursive_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        result: list[str] = []
        for item in value:
            result.extend(recursive_strings(item))
        return result
    if isinstance(value, dict):
        result = []
        for item in value.values():
            result.extend(recursive_strings(item))
        return result
    return []


def extract_telemetry_tokens(payload: Any) -> int | None:
    """Read OpenViking's request-level LLM total without double-counting nested totals."""

    if not isinstance(payload, dict):
        return None
    telemetry = payload.get("telemetry", {})
    summary = telemetry.get("summary", {}) if isinstance(telemetry, dict) else {}
    tokens = summary.get("tokens", {}) if isinstance(summary, dict) else {}
    llm = tokens.get("llm", {}) if isinstance(tokens, dict) else {}
    if not isinstance(llm, dict):
        return None
    total = llm.get("total")
    if isinstance(total, (int, float)):
        return int(total)
    values = [llm.get("input"), llm.get("output")]
    present = [int(value) for value in values if isinstance(value, (int, float))]
    return sum(present) if present else None
