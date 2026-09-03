# MetaOne Deterministic Semantic Construction

## 1. Scope and boundary

MetaOne provides the deterministic semantic backbone for assets that exist in one
current environment. It is authoritative for technical identity, logical/physical
models, dimensions, measures, indicators, catalogs and available lineage that its
interfaces explicitly return.

This is an **Environment Semantic Compiler**, not the global Enterprise Data Context
Compiler and not an ontology. Its output remains in the Environment Knowledge Base and
is read through `MetaOneMcpAdapter` at query time. It MUST NOT be blindly fused into or
written back to the immutable Reference Knowledge Base.

The LLM-facing units remain Rich Context Pages and Context Bundles. The backend graph
is machine-facing and MUST NOT be exposed for node-by-node Agent traversal.

## 2. Target flow

```text
MetaOne primary interfaces
        │
        ▼
Raw domain snapshots + source Evidence
        │
        ▼
Endpoint-specific deterministic normalizers
        │
        ▼
Canonical Environment Nodes + Explicit Edges
        │
        ├── identity resolution / deduplication
        ├── conflict detection / verification reads
        └── derived backrefs and bounded graph indexes
        │
        ▼
Rich Environment Asset Pages + Page-level indexes
        │
        ▼
MetaOne MCP: capabilities / search / read / expand
        │
        ▼
MetaOneMcpAdapter → query-scoped Binding Overlay
        │
        ▼
Explore Context Bundle
```

Parser-first still applies: contract fields and explicit relation records are parsed
deterministically. LLM enrichment may propose business meaning only as `CANDIDATE` and
never manufactures environment existence or technical edges.

## 3. Canonical environment nodes

| Node | Primary source | Important sections |
|---|---|---|
| `Catalog` | `/catalog/v1/catalogList` | identity, parent, path, description, app |
| `LogicalEntity` | `/entity/v1/entityList` | identity, description, subject, catalog |
| `LogicalAttribute` | `/entity/v1/attributeByEntityId` | type, expression, entity, mappings |
| `Dimension` | `/plat/meta/v1/dimensions/` | identity, description |
| `DimensionHierarchy` | `/dimensions/{dimensionName}/hierarchies` | ordered levels |
| `DimensionLevel` | `/dimensions/{dimensionName}/levels` | identity, key/caption semantics |
| `DimensionAttribute` | `/dimensions/{dimensionName}/levels/{levelName}/attributes` | type and level |
| `Measure` | `/measure/v1/measureList` | expression, aggregation, unit, time type, subject |
| `Indicator` | `/indicator/v1/indicatorList` | formula, unit, aggregation levels, subject |
| `IndicatorVariable` | `/indicator/v1/indicatorList` | variable identity and binding expression |
| `PhysicalModel` | `/table/v1/tableList` | datasource, schema, layer, engine, lifecycle |
| `PhysicalColumn` | `/table/v1/columnListById` | type, nullable/key flags, model |
| `AggregateModel` | `/aggregateModel/v1/aggregateModelList` | entity mapping, store-indicator flag |
| `DataFlow` | `/meta/lineage/v2/queryByModel` | name, engine, source model, destination model |

`Catalog` is kept as `Catalog`; it is not automatically promoted to warehouse Layer,
Domain or Subject. Such classification requires an explicit type/path rule with rule
Evidence, otherwise it remains unresolved.

## 4. Deterministic edges

| Edge | Primary fact source |
|---|---|
| `LogicalEntity --HAS_ATTRIBUTE--> LogicalAttribute` | `attributeByEntityId` |
| `LogicalAttribute --MAPS_TO--> PhysicalColumn` | explicit attribute field mapping |
| `LogicalEntity --RELATED_TO--> LogicalEntity` | `entityBuziRelation` |
| `LogicalEntity --USES_DIMENSION--> Dimension` | `levelRelationByEntity` |
| `LogicalAttribute --MAPS_TO_LEVEL--> DimensionLevel` | `levelRelationByEntity` |
| `Dimension --HAS_HIERARCHY--> DimensionHierarchy` | Dimension hierarchies API |
| `Dimension --HAS_LEVEL--> DimensionLevel` | Dimension levels API |
| `DimensionHierarchy --HAS_LEVEL--> DimensionLevel` | Dimension hierarchy definition |
| `DimensionLevel --HAS_ATTRIBUTE--> DimensionAttribute` | Dimension attributes API |
| `DimensionLevel --ROLLS_UP_TO/RELATED_LEVEL--> DimensionLevel` | `levelLineageByEntity` |
| `LogicalAttribute --PROVIDES_MEASURE--> Measure` | `measureEntityRels` |
| `Measure --AVAILABLE_BY--> DimensionLevel` | `measureDimRels` |
| `Measure --CALCULATED_FROM--> Measure` | `measuresRels` |
| `Indicator --CALCULATED_FROM--> Measure` | `indicatorMeasuresRels` |
| `Indicator --AVAILABLE_BY--> DimensionLevel` | explicit `aggreLevels` |
| `Indicator --USES_VARIABLE--> IndicatorVariable` | `indicatorVariableRels` |
| `Indicator --ASSOCIATED_WITH/REFERENCES/DRILL_DOWN/ABNORMAL_DRILL--> Indicator` | `indicatorsRels` |
| `LogicalEntity --IMPLEMENTED_BY--> PhysicalModel` | `phyModelList` |
| `PhysicalModel --HAS_COLUMN--> PhysicalColumn` | `columnListById` |
| `PhysicalModel --UPSTREAM_OF--> PhysicalModel` | lineage v2 `modelLineage` |
| `PhysicalColumn --DERIVES_TO--> PhysicalColumn` | lineage v2 `columnLineages` |
| `PhysicalModel --TRANSFORMED_BY--> DataFlow` | lineage v2 `flowVOS` |
| `AggregateModel --MAPS_TO--> LogicalEntity` | `aggregateModelList` |
| `AggregateModel --SOURCE_MODEL--> PhysicalModel` | `srcPhyModelListByAggregateModel` |
| `Catalog --HAS_CHILD--> Catalog` | catalog parent id |
| `Asset --BELONGS_TO_CATALOG--> Catalog` | explicit asset catalog id |

Forward references are primary. Reverse edges are derived indexes and carry the source
edge Evidence rather than becoming new independent facts.

## 5. Interface authority

### Compiler primary

Primary interfaces build facts. The current P0 inventory is exported as
`METAONE_COMPILER_ENDPOINTS` from `mcp/data-catalog/src/metaone/endpoints.ts`.

### Serving verification and fallback

`/entity/v1/entityColumnRelationById` is a pre-assembled local Semantic Bundle. It is
useful for bounded reads, fast enrichment and consistency checks, but it MUST NOT
overwrite conflicting facts compiled from the primary Entity, Dimension, Measure,
Indicator and Physical domains.

`queryDimTable`, `rollUpDimQuery`, `/meta/levels/list`, runtime counters/indicator
models and legacy lineage are supplemental, fallback or verification sources. A
disagreement becomes a conflict with both Evidence records; it is never blindly
overwritten.

## 6. Evidence and state

Every node and edge retains:

```text
provider
environment_id
endpoint_key and source path
provider object/relation id
captured_at
snapshot_token or high-water mark
assertion_status = EXPLICIT | DERIVED | CANDIDATE
```

Primary contract rows create `EXPLICIT` facts. Reverse indexes and deterministic
catalog/path classification create `DERIVED` facts with rule Evidence. Similarity or
LLM enrichment creates only `CANDIDATE` items.

An empty, unauthorized, timed-out or truncated response never proves absence. Only a
complete authoritative query with an explicit zero result can produce
`NOT_FOUND_CONFIRMED`.

## 7. Incremental publication

Each domain is fetched with its supported update timestamp/high-water mark. Domain
snapshots are normalized first and published together under an immutable environment
snapshot token. A snapshot is queryable only after referential checks complete.

Publication records:

- source capability revision;
- per-domain high-water marks and completeness;
- node/edge counts and rejected-record warnings;
- conflicts and unresolved references;
- environment snapshot token and capture time.

Mixed-revision facts are not silently presented as one complete snapshot.

## 8. Rich Environment Asset Pages

Graph nodes are materialized into a few rich pages rather than many sparse reads.
Examples:

- `Measure Page`: meaning, expression, aggregation, unit, source attributes, available
  dimensions, dependent indicators, Evidence and missing sections;
- `Indicator Page`: formula, measures, related/drill indicators, supported levels,
  physical/logical support paths and Evidence;
- `Physical Model Page`: columns, logical implementation, upstream/downstream tables,
  column lineage, transformation flows, catalog and lifecycle;
- `Dimension Page`: hierarchies, ordered levels, attributes, entity mappings and
  roll-up relationships.

Search is Page-level. Field, relation, lineage and Evidence retrieval are focused
expansions with explicit result budgets.

## 9. Query example

For “5G 流量可以按哪些维度分析，来自哪些表？”:

1. search a `Measure Page` for 5G traffic;
2. expand `AVAILABLE_BY` to Dimension Levels;
3. expand `PROVIDES_MEASURE` back to Logical Attributes;
4. follow `IMPLEMENTED_BY` and attribute/column mappings to Physical Models/Columns;
5. expand lineage only when upstream/downstream explanation is required;
6. join Reference Context business objects, analysis purposes and terminology through
   the query-scoped Binding Overlay;
7. return one Context Bundle with facts, candidates, conflicts, Evidence, coverage,
   missing context, truncation and both environment/reference versions.

## 10. Remaining implementation work

The endpoint inventory, stable four-tool MCP surface, normalized fixtures and
configurable API-gateway transport are implemented. The transport covers authentication,
GET/POST routing, query/body argument mapping, bounded fan-out, timeout/error handling and
strict normalized-envelope validation.

Production completion still requires real request/response fixtures for each published
P0 route, endpoint-specific raw-payload normalizers, gateway/OpenAPI method and parameter
verification, incremental publication, Rich Environment Asset Page materialization and
bounded read/expand orchestration in Explore. Keep
`livePayloadMappingVerified: false` until those fixtures pass integration tests.
