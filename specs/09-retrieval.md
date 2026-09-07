# High-information Context Serving (v3)

The Serving projection preserves Template Contract, Canonical Context, Rich Context
Page, and the four tools. Graph remains internal. Golden fixtures never enter the
production index. Initial search indexes Pages; Element retrieval is scoped to
already selected Pages.

## Hybrid Page Retrieval

`PageIndex.search` fuses exact identifier/name/alias matches, BM25, cosine vector
similarity and governed facets using weighted reciprocal rank fusion (weights
3/1/1/0.25, RRF constant 60). The default trained encoder is FastEmbed 0.8.0 with
`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`, installed through
the `dense` extra. Its passage/query encoders run locally. Model name and package
version appear in serving metadata; model caches are external to governed snapshots.
`DATA_CONTEXT_DENSE_MODEL` selects a different supported model or `disabled`;
`DATA_CONTEXT_DENSE_LOCAL_ONLY=1` forbids uncached model loading. The historical
concept/hash encoder remains an explicit fixture ablation and is never labeled dense.
Custom encoders implement `version`, `encode(list[str]) -> list[list[float]]` and
optionally `encode_query(str) -> list[float]`. All vectors are rebuilt on index mutation/reload; malformed or
failed encoding falls back to lexical retrieval with an explicit warning.

`PageIndex(mode="baseline")` retains the old lexical candidate scorer for a
retrieval ablation. This ablation uses the new runtime, not the historical runtime.
Candidates and inferred identities are excluded from every retrieval channel.
Model layer/domain/topic constraints also apply during relation completion.
An underscore inside a field identifier does not create a classification filter.
An exact technical identifier cannot gain candidates from dense/facet similarity
alone. `anchor_candidates` records the ranked initial Pages before hydration,
diversity, seen-page and bundle limits; `anchor_context_ids` follows that ranking.

`BundleAssembler` completes confirmed typed references and backrefs on the machine
side: one hop normally, two for metric/model, requirements and impact intents,
with at most `max(8, 6 * seed_count)` candidates. It ranks by relevance, marginal
aspect information and type diversity. These aspect hints only rank candidates;
they are not Coverage assertions. `bundle_k`, per-type limits, seen paths, and
L1-to-L0 token fallback control hydration. Hops never become LLM tool calls.

## Searchable Element Index

`data_expand(paths, expand=["fields"], query="subscriber_key", top_k=20)` searches
only governed elements of those Pages. Results have stable element IDs, parent
path, section, offset, value, score, status and source evidence. `kind` distinguishes
Field, Attribute, Formula, Counter and JoinKey. `parent_context` contains the parent
Page's path, name, type, L0 text and REFERENCE layer. `identifiers` and `match`
distinguish exact identity matches from descriptive text. Supported sections
include fields, counters, formula, grain, dimensions, metrics, joins, constraints
and business mappings. Explicit and derived sections are searchable; candidate
sections and nested candidate assertions are not. JSON property names are not
searchable content. Aliases include fields, attributes, formulas, counters and
join_keys; `elements` searches all element sections within the selected Pages.
`ElementIndex.search` also supports machine-side whole-index queries with parent
results; this does not add a fifth LLM tool or put field text in initial Page search.
`top_k` bounds returned lists; `section_totals` and `truncated`
make incomplete dictionaries visible. Query hits take priority over list order.

`related`, `lineage`, `impact`, and `backrefs` return bounded rich context summaries
with typed relation and evidence, rather than raw graph edges. `lineage` uses a
lineage predicate whitelist; arbitrary associations cannot satisfy lineage.

## Budgets and compatibility

The four names remain `data_search`, `data_read`, `data_expand`, `data_source`.
Search adds optional `intent`; expand adds `query`, `intent`, `token_budget`.
MCP input schemas and Python producers/consumers are updated together.

Search `token_budget` applies to hydrated Page content and its support metadata.
Expansion has a separate token budget and omits whole sections if necessary.
It never retains the support proof of an omitted section. Small metadata envelopes
and the final assembled bundle are not part of either hydration limit. Telemetry
reports the full serialized tool responses separately; these are token estimates,
not a tokenizer measurement or monetary cost. The runtime performs one search and
at most one focused expand. Environment calls are separately accounted for.
