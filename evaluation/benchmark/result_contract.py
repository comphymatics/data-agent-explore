"""Public E2E inputs contain no Gold or evaluation aliases."""
from dataclasses import asdict, dataclass, field
from typing import Any, Protocol

SYSTEMS = ("llm_wiki", "opencode_native", "opencode_openviking", "data_explore")
ENTITY_TYPES = ("scenarios", "purposes", "metrics", "dimensions", "business_objects",
                "logical_models", "physical_models", "fields")
CATEGORIES = ("Q1", "Q2", "Q3", "Q4", "Q5", "Q6")


@dataclass(frozen=True)
class BenchmarkCase:
    case_id: str
    query: str


@dataclass(frozen=True)
class QueryBudget:
    max_output_tokens: int = 2048
    timeout_seconds: int = 300
    context_tokens: int = 8000


@dataclass(frozen=True)
class RunContext:
    run_id: str
    repeat: int
    workspace: str
    corpus_fingerprint: str
    model: dict
    hardware_class: str
    smoke: bool = False


@dataclass
class BuildResult:
    system: str
    status: str
    build_tokens_input: int | None = None
    build_tokens_output: int | None = None
    build_tokens_total: int | None = None
    build_time_ms: int = 0
    storage_bytes: int | None = None
    metadata: dict = field(default_factory=dict)
    trace: list = field(default_factory=list)


@dataclass
class QueryResult:
    system: str
    case_id: str
    status: str
    raw_output: Any = None
    query_tokens_input: int | None = None
    query_tokens_output: int | None = None
    query_tokens_total: int | None = None
    tool_calls: int | None = None
    retrieval_rounds: int | None = None
    latency_ms: int = 0
    trace: list = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


class BenchmarkAdapter(Protocol):
    name: str

    def prepare(self, corpus_path: str, run_context: RunContext) -> BuildResult: ...
    def query(self, case: BenchmarkCase, budget: QueryBudget, run_context: RunContext) -> QueryResult: ...
    def cleanup(self) -> None: ...


def record(value):
    return asdict(value)
