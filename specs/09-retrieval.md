# Retrieval
Scope Routing -> multi-index candidate retrieval -> reranking -> diverse Context Bundle -> coverage hints.
Initial bundle aims for several complementary rich pages.
Focused expansion retrieves fields, formulas, joins, lineage, constraints, evidence, mappings or runtime details.

For requirement research and model design, asset selection is environment-first:

1. search and expand MetaOne through the Environment Binding adapter;
2. classify each requirement as found, partial, confirmed missing, unsupported,
   unavailable or truncated;
3. enrich returned environment assets with reference scenarios, business objects, SID
   and modeling semantics;
4. use reference assets as alternatives only after confirmed environment absence, and
   label them `REFERENCE_ONLY` rather than available assets.

See `15-dual-layer-knowledge.md`. Environment failures never become negative facts.
