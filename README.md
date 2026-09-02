# Data Agent Explore — Complete Reference Implementation

This repository contains a complete, runnable implementation of two logical modules:

1. **Enterprise Data Context** — validates parser-delivered Template JSON and compiles it into traceable Rich Context Pages, indexes, references and a machine-side graph; local raw-source parsers remain development compatibility utilities.
2. **Explore Agent** — understands a query, retrieves a Context Bundle, checks coverage, performs focused expansion, and returns reusable data context.

The intended topology is **Main Agent → Explore SubAgent → four read-only Context
tools**. MCP is a transport for those tools; Enterprise Data Context remains a
deterministic Context Engine and does not answer user questions.

## Core rules

- Graph for machines; Pages for LLMs.
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

The MetaOne-facing fixture under `mcp/data-catalog/` now exposes only four read-only
environment operations: capabilities, asset search, bounded asset read and focused
relation expansion. Its reviewed endpoint inventory treats
`/entity/v1/entityColumnRelationById` as the P0 deterministic semantic backbone and
adds P1 expansion for model-dimension relations, dimension hierarchy, aggregate-model
sources and physical lineage. The endpoint inventory is verified from interface
descriptions only; request methods, authentication and raw response-field mappings
remain unverified until real JSON samples are captured.

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
    "继续补充尚未读取的模型上下文",
    token_budget=1600,
    state=first.exploration_state,
)
```

The state pins `IndexVersion`, carries coverage and seen Context IDs, and prevents
silent cross-version replay. It is part of the Context Bundle contract in
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
