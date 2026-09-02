# Development Guide

Before changing code:

1. Read `AGENTS.md`.
2. Read the relevant `specs/`.
3. Inspect schema contracts in `enterprise_data_context/models.py`.
4. Treat `source-materials/` as partial immutable input.
5. Inspect existing tests.
6. Preserve end-to-end behavior.

The production parser boundary is the five Template JSON delivery shapes under
`source-materials/templates/`, governed by `contracts/template-input.schema.json`.
`ContextFragment` is an internal normalized IR, not a parser-team deliverable.

## Extension points

Real-document differences MUST be handled through these extension points first:

- `ExtractorProfile`
- `SemanticExtractor`
- `BusinessMappingRule`
- `SourceAuthorityPolicy`
- `EnvironmentBindingAdapter`

MetaOne integrations must enter through `MetaOneMcpAdapter` and the minimal
`McpToolClient` port. Do not import provider tool names or raw payload fields into
Explore. Fixture-validated adapters remain pending live verification until their real
tool schemas, errors, pagination and version fields have been captured in a connected
environment.

Do not redesign the pipeline for a new document layout unless the structural parser itself is genuinely insufficient.

## Definition of done

A change is complete only when:
- tests pass;
- evidence remains traceable;
- conflicts/uncertainty are preserved;
- missing context remains explicit;
- no graph-first, ontology-first or raw-chunk-first architecture is introduced.
