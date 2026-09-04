# Acceptance
Required E2E path:
source -> external parse/extract -> Template JSON delivery -> schema validation ->
internal ContextFragment normalization -> canonicalize -> fuse -> page ->
indexes/graph -> search -> Explore -> Context Bundle.

The implementation must remain useful with partial source materials and must explicitly report missing context.

The parser delivery gate must reject any data file that does not conform to
`contracts/template-input.schema.json`. Direct ContextFragment JSON/JSONL is an
internal compatibility path and is not required from the parser team.

Real parser batches must additionally pass `scripts/validate_template_delivery.py`.
Missing batch metadata keeps coverage `PARTIAL`; a `COMPLETE` claim requires an exact,
fingerprinted and explicitly authoritative `delivery-manifest.json`. The resulting
delivery report must be persisted with the immutable Context snapshot.

## Dual-layer MetaOne acceptance

Before enabling a concrete MetaOne adapter in production, tests must prove that:

- MetaOne environment assets win for existence, identifiers and technical metadata;
- reference semantics enrich a found environment asset without replacing its facts;
- only `NOT_FOUND_CONFIRMED` enables a `REFERENCE_ONLY` asset alternative;
- timeout, unauthorized, unsupported and truncated results remain unknown/missing;
- MCP tool addition does not break the consumer, and tool removal is capability-gated;
- normalized responses retain environment, provider revision/snapshot and Evidence;
- deterministic mappings are `DERIVED`, inference remains `CANDIDATE`, and review is
  required before a candidate becomes a confirmed binding;
- a Context Bundle exposes reference, environment and binding-policy version axes.
