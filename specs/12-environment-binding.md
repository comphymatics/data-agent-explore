# Environment Binding

Global Reference Context describes semantic requirements and canonical model roles.
Current-environment assets are resolved late from MetaOne through a capability-negotiated
adapter. MetaOne remains authoritative for current existence, identifiers and technical
metadata; Reference Context supplies scenarios, requirements, business objects, SID and
modeling semantics.

The runtime creates a query-scoped Binding Overlay. It does not fuse MetaOne data into
the immutable global Reference Context snapshot. The adapter must distinguish confirmed
absence from unsupported, unavailable and truncated responses before reference-only
fallback is allowed.

The repository now contains a capability-negotiated `MetaOneMcpAdapter`, normalized
availability/result contracts, intent-driven environment-first lookup and a query-scoped
Binding Overlay. The adapter accepts a minimal MCP client port so transport, credentials
and deployment details remain outside the domain layer. It discovers compatible tools,
maps parameter aliases, normalizes environment assets and preserves provider evidence.

This implementation is validated against local fixtures only. A connected MetaOne
environment is still required to calibrate real tool schemas, authentication behavior,
pagination, limits, freshness/version fields and error payloads. Until that verification
is complete, the integration status is `fixture-validated / pending live verification`.
See `15-dual-layer-knowledge.md` for the authority rules and remaining phases.

## Serving overlay v2

`environment-binding/v2` separates three independently evidenced collections:

- `identity_bindings`: unique explicit provider `attributes.reference_path`
  crosswalks with matching asset type, environment ID and snapshot evidence.
  Duplicate crosswalks, missing snapshots and cross-type matches remain unconfirmed.
- `semantic_mappings`: explicit `MAPS_TO` / `SEMANTIC_MAPPING` relations. Semantic
  alignment does not establish asset identity.
- `structural_relations`: other explicit environment relations whose endpoints are
  in the returned environment asset set. Structural adjacency does not establish
  semantic alignment or identity.

Name/code/alias equality only yields `CANDIDATE` bindings, including previously
accepted same-name derived bindings. The legacy `confirmed_bindings` projection
contains identity bindings; `derived_bindings` is empty under this policy.
All unbound reference assets appear in `reference_only_assets` with the actual
availability state. Their reference semantics remain reference knowledge; they
must not be advertised as available current-environment assets.

A normalized provider may return `requirement_coverage` assessments for an exact
`entity`, `aspect`, optional `selector`, `status` and `evidence`. `MISSING` also
requires `complete: true` and `authoritative: true`. Global `total=0` remains a
query availability result and is insufficient to infer individual missing fields.
The adapter propagates normalized requirement assessments; it does not guess
private MetaOne payload mappings. Explore requests at most one expansion batch
covering two environment anchors, or at most two bounded reads as a fallback.
Live HTTP/auth/raw payload calibration remains a separate integration gate.
