"""Public E2E inputs contain no Gold or evaluation aliases."""
from dataclasses import asdict, dataclass, field
from typing import Any, Protocol

SYSTEMS = ("llm_wiki", "opencode_native", "opencode_openviking", "data_explore")
ENTITY_TYPES = ("scenarios", "purposes", "metrics", "dimensions", "business_objects",
                "logical_models", "physical_models", "fields")
CATEGORIES = ("metric_to_model", "purpose_to_data", "model_to_analysis", "model_to_business",
              "field_discovery", "lineage_impact", "negative")
RELATION_TYPES = ("supported_by", "requires_metric", "requires_dimension", "belongs_to_object",
                  "implemented_by", "upstream", "downstream")
OUTPUT_SCHEMA = "data-explore-eval-result/v1"


@dataclass(frozen=True)
class BenchmarkCase:
    case_id: str
    query: str


@dataclass(frozen=True)
class QueryBudget:
    """Native context budget is adapter-specific, never a shared hard limit."""
    max_output_tokens: int = 2048
    timeout_seconds: int = 300
    native_context_budget: int = 8000


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
    build_llm_input_tokens: int | None = None
    build_llm_output_tokens: int | None = None
    build_llm_total_tokens: int | None = None
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
    query_llm_input_tokens: int | None = None
    query_llm_output_tokens: int | None = None
    query_llm_total_tokens: int | None = None
    tool_calls: int | None = None
    retrieval_rounds: int | None = None
    latency_ms: int = 0
    trace: list = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    delivered_context_tokens: int | None = None
    output: dict | None = None


class BenchmarkAdapter(Protocol):
    name: str

    def prepare(self, corpus_path: str, run_context: RunContext) -> BuildResult: ...
    def query(self, case: BenchmarkCase, budget: QueryBudget, run_context: RunContext) -> QueryResult: ...
    def cleanup(self) -> None: ...


def record(value):
    return asdict(value)
