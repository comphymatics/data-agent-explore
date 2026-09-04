# Dual-layer Knowledge and MetaOne Binding

## 1. Objective

The system uses two logically separate knowledge layers:

1. **Reference Knowledge Base (RKB)** — a global, versioned semantic baseline
   compiled from parser-delivered Template JSON, SID and governed modeling
   standards.
2. **Environment Knowledge Base (EKB)** — tenant/environment-specific metadata
   read from MetaOne through an adapter at query time.

The two layers MUST NOT be blindly fused into one global snapshot. MetaOne is
volatile and environment-specific; the reference snapshot is versioned and reusable.
A query creates a temporary **Binding Overlay**, not a third source of facts.

## 2. Responsibilities

### Reference Knowledge Base

The reference layer is authoritative for reusable semantic material that is not an
assertion about the current environment:

- scenarios, requirements and analysis purposes;
- business objects and attributes;
- SID vocabulary, aliases and approved mappings;
- modeling-layer/domain/topic rules;
- reference metric, dimension, measure and model definitions;
- reference relationships, evidence, conflicts and known gaps.

Its immutable version is `referenceIndexVersion` (the existing `IndexVersion`).

### Environment Knowledge Base

MetaOne is authoritative for current-environment facts it actually returns:

- asset existence and stable environment identifiers;
- dimensions, measures, indicators and their current definitions;
- logical models, physical models, fields and relationships;
- available lineage, ownership, lifecycle and deployment metadata;
- environment/tenant scope and provider freshness information.

MetaOne responses MUST retain environment evidence such as provider, environment,
captured time and provider revision/snapshot token. Reference content MUST NOT be
used to claim that an asset exists in the current environment.

## 3. Authority is field-level, not database-level

| Context section | Primary authority | Reference contribution | Fallback rule |
|---|---|---|---|
| Environment asset existence, ID, fields, lineage | MetaOne | aliases and semantic hints only | never manufacture an environment fact |
| Current metric/dimension/measure/model definition | MetaOne when present | explain, compare and identify gaps | reference item is `REFERENCE_ONLY` if environment absence is confirmed |
| Scenario, requirement, analysis purpose | governed reference material / confirmed research | MetaOne assets may support it | no reverse promotion from asset similarity |
| Business object and SID meaning | SID and governed reference knowledge | bind environment logical/physical assets | unreviewed mapping remains `CANDIDATE` |
| Layer/domain/topic classification | explicit MetaOne declaration, else approved modeling rule | rules and canonical vocabulary | deterministic rule is `DERIVED`; semantic inference is `CANDIDATE` |

When both layers provide the same section, the system preserves both evidence chains
and applies a section-specific authority policy. It never performs object-level
last-write-wins merge.

## 4. Environment-first query policy

For requirement research and model design, the query sequence is:

1. Parse intent and required coverage into semantic requirements.
2. Discover the MetaOne adapter capabilities for the current session/environment.
3. Search MetaOne for environment anchors first.
4. Read/expand only the selected environment assets under explicit budgets.
5. Classify each required coverage item using the state model below.
6. Use the Reference Knowledge Base to enrich meanings, scenarios, business objects,
   SID alignment and modeling classification.
7. If the environment definitively lacks an asset, optionally retrieve reference
   alternatives as `REFERENCE_ONLY` candidates.
8. Assemble a Binding Overlay and return a Context Bundle with both version axes.

Reference semantic enrichment still occurs when MetaOne finds an asset. The fallback
rule controls **asset selection**, not whether semantic reference knowledge may be
used to explain an existing environment asset.

## 5. Availability state model

The adapter must distinguish these states:

| State | Meaning | May use reference asset as fallback? |
|---|---|---|
| `FOUND` | Environment asset and evidence returned | no; enrich the environment asset |
| `PARTIAL` | Asset returned but requested details are incomplete | only fill semantics; keep environment gaps explicit |
| `NOT_FOUND_CONFIRMED` | Complete, scoped search says no matching asset exists | yes, as `REFERENCE_ONLY` candidate |
| `UNSUPPORTED` | Provider cannot answer the requested operation/type | no; availability is unknown |
| `UNAVAILABLE` | Timeout, connection, authorization or provider failure | no; availability is unknown |
| `TRUNCATED` | Provider budget/page limit prevented a complete result | no; continue or report incomplete |

`UNSUPPORTED`, `UNAVAILABLE` and `TRUNCATED` MUST NOT be converted to
`NOT_FOUND_CONFIRMED`. Absence of evidence is not evidence of absence.

## 6. Stable adapter boundary for a changing MCP

Explore and the Reference Context Engine MUST NOT depend on MetaOne MCP tool names or
raw response fields. A `MetaOneMcpAdapter` acts as an anti-corruption layer and exposes
a small platform-neutral port:

```text
describe_capabilities(environment) -> CapabilitySnapshot
search_assets(requirements, cursor, budget) -> EnvironmentSearchPage
read_asset(asset_ref, sections) -> EnvironmentAsset
expand_assets(asset_refs, relations, budget) -> EnvironmentExpansion
```

The concrete adapter owns:

- MCP tool discovery and capability negotiation;
- mapping current tool names/parameters to stable operations;
- response validation and normalization;
- pagination, timeouts, authentication-category errors and truncation;
- mapping MetaOne asset types to canonical context types;
- attaching environment Evidence and provider version information.

Optional operations are capability-gated. Adding or removing a MetaOne MCP interface
therefore changes the adapter mapping and fixtures, not Explore prompts, Reference
Context contracts or retrieval policies.

The sample under `mcp/data-catalog/` is an integration fixture, not the authoritative
MetaOne interface contract. Its current tool count, endpoint paths and response fields
MUST NOT be copied into the stable domain contract.

The fixture exposes the environment-side capability shape as four operations:
`metaone_get_capabilities`, `metaone_search_assets`, `metaone_get_asset`, and
`metaone_expand_assets`. The source-interface inventory is maintained separately in
`mcp/data-catalog/src/metaone/endpoints.ts` and labels every interface by Compiler or
Serving phase and by primary, supplemental, fallback or verification authority.
`/plat/meta/v1/dimensions/`, explicit Entity/Level relations, Measure/Indicator
relations and lineage v2 are primary Compiler sources.
`/entity/v1/entityColumnRelationById` is a Serving-time assembled bundle used for fast
read and consistency checks, not the Compiler fact authority. This inventory does not
assert unobserved authentication or JSON field mappings.

## 7. Binding Overlay

The overlay is query-scoped and contains:

```text
environment_facts[]       MetaOne-backed current facts
reference_semantics[]     versioned explanations and canonical meanings
confirmed_bindings[]      explicit or reviewed cross-layer mappings
derived_bindings[]        deterministic rule output with rule evidence
candidate_bindings[]      inference/similarity output, never normal facts
reference_only_assets[]   alternatives not verified in the environment
conflicts[]               section-level disagreements
missing_context[]         unresolved semantic or environment requirements
```

The overlay may be cached by
`environment + tenant + capabilityRevision + environmentSnapshot + referenceIndexVersion + policyVersion`.
It must not be written back into the global Reference Knowledge Base automatically.

## 8. Context Bundle version and provenance

A dual-layer bundle should expose:

- `referenceIndexVersion`;
- `environment.provider` and `environment.environmentId`;
- `environment.capabilityRevision`;
- `environment.snapshotToken` or `capturedAt`;
- `bindingPolicyVersion`;
- per-item `knowledgeLayer` (`ENVIRONMENT`, `REFERENCE`, `BINDING`);
- per-item `assertionStatus` and Evidence;
- availability state, truncation and provider warnings.

The bundle contract now exposes `reference_index_version`,
`binding_policy_version`, the normalized `environment` version fields and
`binding_overlay`. The existing `index_version` remains as a backward-compatible alias
for the reference snapshot version.

## 9. GAP assessment against the current sample

The checked-in sample is useful for validating MCP transport and provider separation,
but it is not yet the target dual-layer implementation:

- `DataCatalogProvider` returns broad `Record<string, unknown>` values for capability,
  search and context operations, so response compatibility is not validated;
- `HttpDataCatalogProvider` binds directly to fixed `/v1/...` endpoints;
- fixture asset and relation types are derived from the reviewed endpoint inventory,
  but live provider capability negotiation still needs calibration;
- the normalized HTTP gateway contract is fixture-only and still needs a production
  provider implementation over real MetaOne payloads;
- the mock dataset mixes SID, analysis purposes and physical environment assets in one
  graph, so it cannot demonstrate two-layer authority or fallback rules;
- the local adapter has not been calibrated against a live MetaOne tool list, payload,
  authentication model, pagination behavior or operational limits;
- Explore performs environment search first, but focused read/expand of selected assets
  is not yet part of its bounded orchestration loop;
- the Binding Overlay supports exact deterministic bindings and guarded reference-only
  candidates, but field-level section authority and cross-layer conflict policies remain
  incomplete;
- governed offline semantic inference now produces bounded, Evidence-backed
  `CANDIDATE` relations; human review/confirmation and overlay caching are not yet
  implemented.

These are implementation GAPs, not reasons to expose raw MetaOne MCP responses to the
Agent. They should be addressed inside the adapter and orchestration layers.

## 10. Recommended implementation phases

### Phase A — contract and adapter fixtures (implemented locally)

- define normalized capability/search/read/expand fixtures;
- implement `MetaOneMcpAdapter` against the current sample;
- add fixtures for renamed/removed/optional MCP tools;
- verify timeout, unauthorized, unsupported and truncated behavior.

### Phase B — environment-first orchestration (partially implemented)

- replace keyword-triggered Environment Binding with intent/policy-driven lookup;
- implement availability and coverage state machines;
- add field-level authority and candidate isolation;
- extend Context Bundle with dual-version provenance.

### Phase C — governed semantic derivation

- add deterministic SID/modeling-rule mappings first;
- add semantic inference only into candidate bindings (implemented for the Reference
  Context snapshot through `build_semantic_candidates.py`);
- introduce review/confirmation workflow and Golden Dataset cases;
- cache overlays without contaminating either source layer.

## 11. Current implementation boundary

Currently implemented in this repository:

- versioned Reference Knowledge compilation and retrieval;
- four read-only Data Context tools;
- normalized environment contracts and `contracts/environment-binding.schema.json`;
- a capability-negotiated `MetaOneMcpAdapter` over a transport-neutral MCP client port;
- fixtures covering current/renamed tools, unsupported operations, timeout, unknown
  completeness and confirmed absence;
- intent-driven environment-first search and availability/coverage states;
- query-scoped Binding Overlay, guarded `REFERENCE_ONLY` candidates and dual-version
  Context Bundle fields;
- a generic data-catalog MCP/provider sample.
- a phase/authority-labeled MetaOne endpoint inventory and deterministic semantic
  construction design in `16-metaone-semantic-construction.md`.

Not yet implemented:

- live MetaOne transport/authentication configuration and contract calibration;
- bounded read/expand orchestration and pagination continuation inside Explore;
- complete field-level authority/conflict handling;
- production LLM/provider calibration, human review workflow and overlay cache.
