# Development Guide

Before changing code:

1. Read `AGENTS.md`.
2. Read the relevant `specs/`.
3. Inspect schema contracts in `enterprise_data_context/models.py`.
4. Treat `source-materials/` as partial immutable input.
5. Inspect existing tests.
6. Preserve end-to-end behavior.

## Extension points

Real-document differences MUST be handled through these extension points first:

- `ExtractorProfile`
- `SemanticExtractor`
- `BusinessMappingRule`
- `SourceAuthorityPolicy`
- `EnvironmentBindingAdapter`

Do not redesign the pipeline for a new document layout unless the structural parser itself is genuinely insufficient.

## Definition of done

A change is complete only when:
- tests pass;
- evidence remains traceable;
- conflicts/uncertainty are preserved;
- missing context remains explicit;
- no graph-first, ontology-first or raw-chunk-first architecture is introduced.
