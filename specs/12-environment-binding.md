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
