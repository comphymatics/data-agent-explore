from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class ExplorationState:
    """Serializable resume token for read-only, multi-round exploration."""

    index_version: str | None = None
    seen_context_ids: list[str] = field(default_factory=list)
    coverage: dict[str, dict[str, Any]] = field(default_factory=dict)
    serving_version: str | None = None
    query_signature: str | None = None
    environment_snapshot: str | None = None
    rounds: int = 0
    used_tokens: int = 0
    last_intent: str | None = None
    stop_reason: str | None = None

    @classmethod
    def from_value(cls, value: ExplorationState | dict[str, Any] | None):
        if value is None:
            return cls()
        if isinstance(value, cls):
            return cls(**asdict(value))
        if isinstance(value, dict):
            allowed = set(cls.__dataclass_fields__)
            unknown = set(value) - allowed
            if unknown:
                raise ValueError(f"unsupported exploration state fields: {sorted(unknown)}")
            return cls(**value)
        raise TypeError("state must be an ExplorationState, mapping, or None")

    def to_dict(self):
        return asdict(self)
