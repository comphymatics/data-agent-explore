# Data Agent Explore — Complete Reference Implementation

This repository contains a complete, runnable implementation of two logical modules:

1. **Enterprise Data Context** — validates parser-delivered Template JSON and compiles it into traceable Rich Context Pages, indexes, references and a machine-side graph; local raw-source parsers remain development compatibility utilities.
2. **Explore Agent** — understands a query, retrieves a Context Bundle, checks coverage, performs focused expansion, and returns reusable data context.

The intended topology is **Main Agent → Explore SubAgent → four read-only Context
tools**. MCP is a transport for those tools; Enterprise Data Context remains a
deterministic Context Engine and does not answer user questions.

## Core rules

- Graph for machines; Pages for LLMs.
- Hierarchies for governed browse/facet organization; typed references for facts.
- Parser-first, LLM-assisted, Agent-evolved.
- Source materials are allowed to be incomplete.
- Absence of evidence is never evidence of absence.
- Explore Agent never reads raw Word/Excel and never traverses raw graph nodes.
- Environment-specific physical-model binding is an adapter boundary, not part of the global context model.
- MetaOne is authoritative for current-environment assets; Reference Context enriches
  their semantics but cannot prove that an asset exists in the current environment.

## Quick start

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate

pip install -e .[dev]
pytest -q
python scripts/demo.py
```

## Compatibility raw-source path

The repository keeps a lightweight local parser for fixtures and development
experiments. It is not the cross-team production delivery boundary:

```bash
python scripts/build_context.py --source-dir source-materials --out generated
```

## Parser delivery contract

The external parser delivers the five JSON structures demonstrated in
`source-materials/templates`: presales
APP features, KPI/KQI definitions, physical tables, modeling analysis definitions,
and the SID business-object knowledge base. This directory structure and its JSON
shapes are the stable cross-team boundary. The parser does not deliver
`ContextFragment` JSON/JSONL.

Files containing `Schema` in their name are shape documentation and are never
ingested as facts or interpreted as instructions.

The machine-valid union contract is `contracts/template-input.schema.json`. Build a
versioned snapshot directly from one compatible JSON file or a directory:

```bash
python scripts/build_template_inputs.py \
  --input source-materials/templates \
  --out generated
```

This path starts after parsing: it validates every delivered data file against the
packaged union schema and normalizes the five external shapes into evidence-bearing
internal `ContextFragment` IR with JSON-pointer locations. Canonical Resolution,
section-level Fusion, Rich Context Page materialization, indexes, graph and read-only
retrieval remain downstream responsibilities. Unknown references remain unresolved
and missing input remains explicit.

For a real parser batch, validate the directory before publication:

```bash
uv run --isolated --extra dev python scripts/validate_template_delivery.py \
  --input parser-delivery-directory \
  --report delivery-validation.json
```

The optional `delivery-manifest.json` lists the batch ID, coverage scope, exact JSON
file inventory, detected kind and SHA-256 fingerprint. A batch without this manifest
remains `PARTIAL`; `COMPLETE` requires `inventory_authoritative=true` and an exact
inventory match. Validation output follows
`contracts/template-delivery-report.schema.json` and is persisted as
`delivery-report.json` in the immutable snapshot.

For the first real-data pilot, follow `specs/19-real-data-pilot-runbook.md`. The
`scripts/audit_context_snapshot.py` command turns quality errors, Evidence completeness,
candidate isolation, cross-source links, unresolved references and orphan Contexts into
explicit pass/fail gates with scope-specific thresholds.

`ContextCompiler.compile_fragments()` and `scripts/build_fragments.py` remain internal
and backward-compatible entrypoints. They are not part of the parser team's delivery
contract.

Saved output is immutable and versioned under `generated/versions/<IndexVersion>`.
`generated/latest.json` is the atomic pointer used by `load_runtime()`.

## Dual-layer knowledge and environment binding

The next-stage design separates two knowledge layers:

- **Reference Knowledge Base** — the immutable Context snapshot built from Template
  JSON, SID and modeling standards. It provides scenarios, requirements, business
  objects, canonical vocabulary and reusable semantic definitions.
- **Environment Knowledge Base** — current tenant/environment metadata queried from
  MetaOne. It is authoritative for dimensions, measures, indicators, logical/physical
  models, fields and other assets that actually exist in that environment.

Requirement research and model design use MetaOne-first asset selection. Reference
Context then enriches those assets with missing semantics. A reference asset is offered
as a fallback only when a complete environment query confirms absence, and remains
`REFERENCE_ONLY`; timeout, authorization failure, unsupported capability and truncated
results are reported as unknown rather than absence.

MetaOne MCP tool names and raw payload fields are deliberately kept outside the stable
domain contract. A capability-negotiated adapter normalizes them before Explore sees
the result, so MCP interfaces may evolve without changing retrieval policy or Context
Bundle semantics. The normalized result is governed by
`contracts/environment-binding.schema.json`. The local adapter implementation is
fixture-validated; real MetaOne transport, authentication, payloads and operational
limits still require verification in a connected environment. The detailed architecture
and remaining implementation GAP are
documented in `specs/15-dual-layer-knowledge.md`.

The MetaOne-facing fixture under `mcp/data-catalog/` exposes only four read-only
environment operations: capabilities, asset search, bounded asset read and focused
relation expansion. Its reviewed endpoint inventory distinguishes authoritative
Compiler sources from Serving shortcuts: `/plat/meta/v1/dimensions/`, explicit
entity-level mappings, Measure/Indicator relations and lineage v2 form the P0
deterministic sources; `/entity/v1/entityColumnRelationById` is a P1 assembled-bundle
verification path. See `specs/16-metaone-semantic-construction.md`. Request methods,
authentication and raw response-field mappings remain unverified until real JSON
samples are captured.

Review assets: `docs/architecture/dual-layer-knowledge-architecture.html` (interactive),
with editable SVG and PNG counterparts in the same directory.

The current end-to-end review view is
`docs/architecture/data-agent-explore-current-complete.html` (interactive), with
editable SVG and PNG counterparts. It combines the external Template JSON handoff,
Reference Context build/runtime, MetaOne capability adaptation, environment-first
Explore policy, query-scoped Binding Overlay, Context Bundle and governance, while
marking each component as implemented, external, MCP sample, partially implemented or
planned.

### Governed model layers and domains

The canonical four-layer model is `ODS / SDL / ODI / ADS`. Incoming `DWD` and
`DWS` are compatibility aliases for `SDL` and `ODI`; canonical Pages and search
facets never store the aliases. Raw declarations are retained alongside the
normalized value with provenance.

The versioned catalog `enterprise_data_context/catalogs/modeling-classification-v3.1.json`
contains the controlled SDL topic domains/topics and ODI object domains/subobjects.
Unknown values are retained as candidates and generate quality warnings instead of
being guessed into the catalog. SID Domain/ABE values use a separate semantic-reference
namespace and do not participate in model-domain filtering.

Classification scope is keyed and uses canonical values:

```python
result = runtime.retrieval.data_search(
    "VoLTE 日模型",
    scope={"layer": "SDL", "topic_domain": "业务", "topic": "VoLTE"},
)
```

### Semantic hierarchy and cross-document associations

`SemanticOrganizationBuilder` derives two complementary runtime views after
Canonical Resolution, section-level Fusion and typed-reference resolution:

- a `HierarchyIndex` for scenario parent/child navigation and governed
  `Layer -> Domain -> Topic/Subobject -> Model` breadcrumbs;
- the existing Backend Graph for confirmed typed references only.

APP `feature_name` and modeling `analysis_type` are both scenario entry points but
retain distinct `scenario.kind` values. Their `app_name` and `analysis_name` parents
retain distinct `semantic_role` values, so source containers are not confused with
governed modeling Topics. Unknown classification values and semantic matches remain
candidates and never create formal hierarchy nodes or graph edges.

The immutable snapshot persists `association-report.json`, including reference
counts by status/relation, confirmed cross-source edges, graph-orphan Contexts and
hierarchy size. Multiline identities are reported for Parser review instead of being
silently rewritten.

Hierarchy and confirmed neighbors are available without adding tools:

```python
search = runtime.retrieval.data_search(
    "高铁场景",
    scope={"scenario_kind": "APP_FEATURE"},
)
path = search["contexts"][0]["path"]
view = runtime.retrieval.data_expand(
    [path], ["hierarchy", "parents", "children", "related"],
)
```

Virtual governed-classification paths such as `hierarchy://models/ODI` can be read
and expanded through the same `data_read` and `data_expand` operations. See
`specs/17-semantic-organization.md` for the relation vocabulary, promotion gates and
acceptance rules.

### Offline semantic visualization

Build the latest Template snapshot and generate the single-file hierarchy +
association browser:

```bash
uv run --isolated --extra dev python scripts/build_template_inputs.py \
  --input source-materials/templates --out generated
uv run --isolated --extra dev python scripts/generate_semantic_context_visualization.py \
  --snapshot generated --output docs/architecture/template-semantic-browser.html
open docs/architecture/template-semantic-browser.html
```

The browser uses a bounded one-hop graph around the selected Rich Context Page.
It does not expose node-by-node graph traversal to the Explore Agent. The left
panel is a browse projection (scenario, model layer/domain/topic and semantic
asset type), while the right panel preserves references, Evidence, candidates,
conflicts and quality warnings from the immutable snapshot.

### Governed LLM semantic candidates

The optional offline inference stage proposes missing relations from APP Features and
modeling analyses to metrics, SID business objects, logical models and physical models.
It reads bounded Rich Page evidence packs and always emits `CANDIDATE` references;
exact target resolution does not promote an LLM proposal to a confirmed Graph edge.

Copy and review `config/llm-inference.example.json`, keep the API key only in the named
environment variable, then run:

```bash
export DATA_CONTEXT_LLM_API_KEY='...'
uv run --isolated --extra dev python scripts/build_semantic_candidates.py \
  --snapshot generated \
  --config config/llm-inference.json \
  --out generated/inference/latest \
  --enriched-out generated-candidates
```

The command writes a schema-validated `inference-report.json` and internal
`candidate-fragments.jsonl`. `--enriched-out` is optional and publishes a separate
immutable candidate snapshot; it never mutates the base snapshot. See
`specs/18-governed-llm-inference.md` for target constraints, Evidence requirements,
coverage semantics and review rules.

## Main runtime API

```python
from enterprise_data_context.runtime import load_runtime
from explore_agent import ExploreAgent

runtime = load_runtime("generated")
agent = ExploreAgent(runtime.retrieval)

bundle = agent.explore("RSRP 有哪些现有模型可以提供？")
print(bundle)
```

`ExploreAgent` now applies an intent-specific `ContextPolicy`. Search hydrates a
small set of Rich Context Pages under a deterministic context-token estimate,
limits repeated context types, and returns explicit budget, novelty and stop
information. The budget covers Context Page hydration, not downstream answer tokens.

For multi-round exploration, pass the returned serializable state explicitly:

```python
first = agent.explore("RSRP 有哪些现有模型可以提供？", token_budget=1600)
second = agent.explore(
    "RSRP 有哪些现有模型可以提供？",  # resume the same query/requirements
    token_budget=1600,
    state=first.exploration_state,
)
```

The state pins `IndexVersion`, serving version and query/requirements, carries
entity-scoped coverage and seen Context IDs, and prevents cross-version replay.
Coverage is reassessed on each run, including after an environment snapshot changes. It is part of the Context Bundle contract in
`contracts/context-bundle.schema.json`; it does not depend on hidden Agent session memory.

## MCP stdio adapter

The dependency-free adapter exposes exactly `data_search`, `data_read`,
`data_expand`, and `data_source` using MCP JSON-RPC over stdio:

```bash
data-context-mcp /absolute/path/to/generated
data-context-mcp /absolute/path/to/generated --index-version context-0123456789abcdef
```

The server writes only MCP messages to stdout. An HTTP transport can wrap the same
`DataContextTools` contract but is intentionally not included in this lightweight
reference implementation.

## Release gates

`save_compiled()` rejects snapshots containing quality errors before creating or
updating `latest.json`; warnings remain publishable. Golden Dataset evaluation is a
separate staging/CI gate so benchmark expectations never become production facts:

```python
from explore_agent.evaluation import assert_golden_gate, evaluate

report = evaluate(agent, cases)
assert_golden_gate(report)
```


## High-information retrieval and Golden regression

Serving v3 adds BM25/exact/dense/facet RRF retrieval, a searchable Page-scoped Element
Index, intent-aware machine relation completion, and requirement/entity Coverage
(`SATISFIED`, `PARTIAL`, `MISSING`, `UNKNOWN`, `NOT_APPLICABLE`). Identity binding, semantic mapping
and structural relations are separate. The four Context Tools remain unchanged
in name. Reference assets retain `knowledge_layer: REFERENCE`.

```python
from explore_agent.coverage import requirement
bundle = agent.explore(
    "Radio Model 的 subscriber_key 字段",
    requirements=[requirement(
        "data://physical-models/radio-model", "fields",
        name="Radio Model", selector="subscriber_key",
    )],
)
print(bundle.coverage)       # requirement records, not booleans
print(bundle.telemetry)      # full tool response estimates and model usage
```

```sh
uv run --isolated --extra dev python -m evaluation.scripts.run_retrieval_golden --gate
# Optional real LLM run against synthetic data using an enabled local configuration:
uv run --isolated --extra dev python -m evaluation.scripts.run_retrieval_golden \
  --semantic-config config/llm-inference.json --output evaluation/retrieval_golden/report-live.json --gate
```

See [Serving](specs/09-retrieval.md), [Runtime and Coverage](specs/10-explore-agent.md)
and [regression scope and metrics](evaluation/retrieval_golden/README.md).
Install `uv sync --extra dense` to enable the default local trained multilingual
encoder (`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`). Set
`DATA_CONTEXT_DENSE_MODEL` to override it, or `disabled` for a lexical-only deployment.
Model files download on first use; page text stays local. After warming the model,
`DATA_CONTEXT_DENSE_LOCAL_ONLY=1` requires cached model files. If dependencies or
weights are unavailable, retrieval falls back with `vector_retrieval_unavailable`.
The concept/hash encoder is now only an explicitly injected historical fixture.

This round freezes Router/Reasoner and validates the lower retrieval layers:

```sh
uv run --isolated --extra dev --extra dense python -m evaluation.scripts.run_retrieval_correctness \
  --dense-model sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 --gate
```

See the [correctness report](evaluation/retrieval_golden/correctness-report.json).
It uses real local embeddings and synthetic source/MetaOne fixtures, not live
environment evidence. No LLM provider participates in this suite.

## Semantic Hierarchy and Progressive Disclosure

The existing organizer now produces Analysis, Domain and Asset views over shared
Canonical Entities, with governed edge status and deterministic L0/L1/L2 aggregate
pages. Explore supports direct, hierarchical and hybrid retrieval inside the same
four read-only tools. See [implementation review](SEMANTIC_HIERARCHY_IMPLEMENTATION.md)
and [contracts and governance](specs/semantic-hierarchy.md).

```bash
# Build from the agreed parser handoff with an explicit organization policy.
uv run --isolated --extra dev python scripts/build_template_inputs.py \
  --input source-materials/templates --out /tmp/context-with-hierarchy \
  --hierarchy-config config/semantic-hierarchy.sample.json

# Rebuild organization over a pinned snapshot; no raw parsing or canonical edits.
uv run --isolated --extra dev python scripts/build_hierarchy.py \
  --snapshot /tmp/context-with-hierarchy --out /tmp/context-reorganized \
  --config config/semantic-hierarchy.sample.json

# Separate synthetic ablation; does not change the official four-system benchmark.
uv run --isolated --extra dev python -m evaluation.hierarchy.run \
  --out /tmp/hierarchy-ablation
```

The sample taxonomy is illustrative. LLM classification is off by default; opt-in
requires `llm_enabled` and `scripts/build_hierarchy.py --llm-config` using the existing
provider configuration. Synthetic gates and ablation do not establish live accuracy
or environment availability.
