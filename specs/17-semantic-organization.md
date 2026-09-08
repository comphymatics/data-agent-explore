# Semantic Organization: Hierarchy + Typed Graph

## 1. Objective

Template JSON sources are organized through two complementary read models:

1. **Hierarchy Index** for browsing, grouping and breadcrumbs;
2. **Backend Graph** for confirmed typed relationships, backrefs and impact.

This is not an ontology. Hierarchy nodes do not become a second fact authority, and
Explore does not traverse graph nodes one by one. Rich Context Page remains the
primary LLM-facing information unit and Context Bundle remains the primary output.

## 2. Scenario hierarchy

The two scenario sources retain their source semantics:

```text
APP / app_name
└── Feature / feature_name              scenario.kind=APP_FEATURE

Analysis Group / analysis_name
└── Analysis Type / analysis_type       scenario.kind=MODELING_ANALYSIS
```

`topic` remains the compatibility Context type for the two source containers. The
`semantic_role` section distinguishes `application` from `analysis-group`; it must
not be interpreted as a governed modeling Topic. Confirmed `part_of` references
derive the parent/child hierarchy. A missing or candidate parent does not enter the
formal hierarchy.

## 3. Multiple semantic organization views

This section is superseded by [Semantic Hierarchy](semantic-hierarchy.md),
[Progressive Disclosure](progressive-disclosure.md) and
[Hierarchical Retrieval](hierarchical-retrieval.md).

Layer, Domain and Topic no longer form one forced tree. Asset View organizes by
layer and models; Domain View organizes by domain/topic/objects; Analysis View
organizes scenarios/purposes/metrics/models. A Canonical Entity may appear in all
three, with sparse levels and multiple organizational parents.

Virtual groups use `data://views/<view>/<kind>/<label>`; old
`hierarchy://models/...` URIs resolve to their respective view groups. Fields stay
in ElementIndex with a bounded important-element preview, not new Rich Pages.

CONFIRMED/DERIVED organization navigates with provenance; CANDIDATE placements are
separate audited overlay records. No placement is promoted into Canonical facts.

## 4. Typed relationship graph

The intended relationship vocabulary includes:

| Source | Relation | Target |
|---|---|---|
| Scenario / Analysis Purpose | `uses_metric` | Metric |
| Metric | `calculated_from` | Counter/Metric |
| Metric | `grouped_by` | Dimension |
| Metric / Dimension | `provided_by` | Logical/Physical Model |
| Physical Model | `implements_logical_model` | Logical Model |
| Physical Model | `implements_metric` | Metric |
| Physical Model | `implements_dimension` | Dimension |
| Logical/Physical Model | `maps_to_business_object` | Business Object |
| Business Object | `represented_by` | Physical Model |
| Physical Model | `upstream_model` | Physical Model |

Only `CONFIRMED` references with a valid target path enter Backend Graph and
Backrefs. Similarity or LLM-assisted mappings remain `CANDIDATE`; targets absent
from the delivery remain `UNRESOLVED`.

## 5. Compiler and serving behavior

After Canonical Resolution, section-level Fusion, semantic mapping and reference
resolution, `SemanticOrganizationBuilder` derives:

- `HierarchyIndex`;
- `association_report`;
- per-Page breadcrumb, parent and child views.

The graph remains rebuildable. Hierarchy contributions, candidate audits, aggregates
and incremental dependencies are persisted in `semantic-organization.json`, so
reload never reruns inference. The association report is persisted separately.

The four stable read-only tools are unchanged:

- `data_search` returns a compact association summary and accepts hierarchy-related
  facets such as `semantic_role`, `scenario_kind` and `application`;
- `data_read` returns a Page hierarchy view, or reads a virtual `hierarchy://` node;
- `data_expand` supports `hierarchy`, `parents`, `children`, `related` and
  `association_report` in addition to existing focused sections;
- `data_source` remains the Evidence boundary for real Context sections.

Explore includes selected scenario hierarchy and confirmed relations in
`analysis_context`, and selected model hierarchy and relations in `data_context`.
It still performs bounded, machine-side expansion instead of raw graph traversal.

## 6. Quality and acceptance

Every build reports:

- references grouped by status and relation;
- confirmed cross-source edges;
- graph-orphan Contexts;
- hierarchy node and edge counts.

Multiline or extremely long canonical names produce
`suspicious_multiline_identity`. This warning identifies parser deliveries where
descriptions or constraints may have been placed in an identity field. It does not
silently rewrite source data.

Acceptance requires:

1. candidate or inferred identities/edges never enter formal indexes or graph;
2. missing model semantics remain unclassified; candidates never navigate as facts;
3. Page breadcrumbs and virtual hierarchy reads are deterministic after snapshot
   save/load;
4. cross-source edge coverage is measured, not fabricated when source materials are
   partial;
5. real-data readiness is assessed with a mutually related Parser delivery batch,
   separately from template fixture validation.
