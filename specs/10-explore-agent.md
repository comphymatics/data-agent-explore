# Explore Runtime: retrieval correctness v3

This revision freezes Router/Reasoner behavior and changes only retrieval,
requirement assessment, identity validation and their evaluation.

Explore returns read-only Context Bundles. It does not answer final analytical
questions, generate SQL, design models, parse original documents, or expose Graph
traversal. It consumes four Context Tools and the Environment Binding adapter.

The runtime routes intent, resolves authoritative environment metadata when
required, retrieves a complementary rich Page bundle, assesses entity-scoped
requirements, performs a bounded focused expansion, then assesses coverage again.
The optional joint reasoner reads only governed Page text, focused sections and
explicit environment descriptions. Final assertions retain their knowledge layer.

## Requirement Coverage

`ContextBundle.coverage` is now a mapping from requirement ID to an assessment:

```json
{
  "field-requirement": {
    "id": "field-requirement",
    "entity": "data://physical-models/radio-model",
    "entity_name": "Radio Model",
    "aspect": "fields",
    "selector": "subscriber_key",
    "layer": "REFERENCE",
    "status": "SATISFIED",
    "evidence": [{"path": "data://physical-models/radio-model", "section": "important_fields"}],
    "reason": "entity_scoped_evidence",
    "context_refs": ["data://physical-models/radio-model"]
  }
}
```

- `SATISFIED`: the requested entity/aspect (and optional specific element) has
  governed, visible evidence in its requested knowledge layer.
- `PARTIAL`: conflicting, ambiguous or incomplete evidence exists.
- `MISSING`: an authoritative provider declares absence for this exact entity,
  aspect and selector with a complete inventory assertion and evidence.
- `UNKNOWN`: evidence is absent or insufficient. Partial source materials, empty
  search, unsupported operations, timeouts and pagination do not prove absence.
- `NOT_APPLICABLE`: explicit, authoritative, evidence-bearing applicability
  assertion for this entity/aspect/selector; never inferred from an empty section.

`CoverageRequirement` is the immutable input model; the existing dictionary helper
and JSON contract remain supported. Every result has `context_refs`. For UNKNOWN
these identify the requested or inspected context, not a claim that it exists;
empty evidence remains visible. Structured section assertions may use
`coverage_status`, `authoritative`, `reason`, optional `selector`, and `complete`
for absence. List-wrapped assertions retain the same semantics. A provider can
return equivalent scoped `requirement_coverage`; conflicting declarations remain
PARTIAL and supplied snapshot identities must agree.

Model A's fields never satisfy Model B. Only whitelisted typed relations can supply
complementary entity context. A Reference Page cannot satisfy an Environment
requirement. Environment-wide boolean coverage is not accepted as entity evidence.
`coverage_summary` is a compatibility projection for reference requirements: an
aspect is true only if **all** its entity requirements are SATISFIED or NOT_APPLICABLE. Consumers
must not apply `bool()` to an assessment object. `missing_context` carries every
unresolved requirement ID plus legacy aspect/gap labels. Explicit Context paths
never fall back to a namesake; ambiguous name matches remain PARTIAL. Selectors
match typed element identifiers, not arbitrary descriptions or JSON keys.

## Typed environment bindings

The online overlay has separate IdentityBinding, SemanticMapping and
StructuralRelation contracts in `contracts/binding-overlay.schema.json`.
Identity requires identical types and a current, evidence-bearing provider
crosswalk, or an explicit stable ID/fully qualified strong key with matching
namespace and environment. Existing Canonical `identity_hints` carry `stable_id`
or `strong_key`, `identity_namespace`, and `environment_id`; the `identity` section
must have EXPLICIT evidence. Serving only projects these fields; it does not alter
Compiler resolution. Provider assets expose corresponding keys in `attributes`.
Names, aliases and `physical_name` hints never establish identity. Multiple assets
for one reference (or the reverse) are ambiguous. Relations require explicit
evidence matching the current environment snapshot. Only explicit identity removes
a Page from `reference_only_assets`; semantic mappings never claim deployment.

Pass explicit `requirements=[{id, entity, entity_name, aspect, layer, selector?}]`
when the caller knows the exact requirements. The bounded router can add grounded
query entities/aspects; deterministic routing preserves missing metric identifiers
in multi-metric queries. A selector tests a particular field/element, not merely
whether some field exists. Resume tokens pin query/requirements and IndexVersion;
coverage is reassessed, not OR-ed across rounds or environment snapshots.

## Bounded semantic components

`ExploreAgent(..., semantic_provider=provider, semantic_limits=SemanticLimits(...))`
enables the optional router and reasoner. Provider contract:
`complete(task, payload, max_output_tokens, timeout_seconds) -> {output, usage?}`.
`HTTPStructuredProvider` supplies a configurable JSON chat-completions transport;
credentials come from an environment variable. No live endpoint is enabled by
default and there are no retries or tool-capable prompts.

Each component makes at most one call per exploration; defaults are 4,000 estimated
input tokens, 600 estimated output tokens and 10 seconds. A shared two-worker cap
bounds outstanding requests. A timed-out provider thread may continue until the
transport returns; its slot remains occupied, and the runtime returns immediately
with a deterministic fallback. Invalid JSON shapes, unsupported intent, invented
entities, excessive output and fake citations also fall back. A model cannot
remove an explicit deterministic intent or weaken the environment availability gate.

The joint reasoner selects up to eight evidence-linked excerpts across rich pages
and environment records. Each excerpt must occur verbatim in its cited record;
the runtime attaches layer, path and evidence. It cannot promote candidates,
change Coverage, create identity bindings or manufacture factual prose. This
first bounded implementation performs evidence selection/comparison rather than
unconstrained generative inference. `reasoning_observations` and `telemetry` expose
accepted outputs, fallback reasons, estimated payload cost and provider usage when
available.

`serving` records retrieval, encoder and Coverage versions independently of the
Canonical snapshot. In-memory corpora receive a content fingerprint; resume tokens
also reject a changed encoder/serving version.
