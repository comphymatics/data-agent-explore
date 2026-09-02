import type { AssetType } from "../domain/types.js";

export type MetaOnePriority = "P0" | "P1";

export interface MetaOneEndpointCapability {
  key: string;
  path: string;
  priority: MetaOnePriority;
  role: "search" | "read" | "expand";
  assetTypes: AssetType[];
  relations: string[];
  description: string;
  runtime: "design" | "runtime" | "cross-service";
}

/**
 * Interface-derived capability inventory. This is routing metadata, not a claim
 * about the as-yet-unverified request method or response JSON shape.
 */
export const METAONE_ENDPOINTS: readonly MetaOneEndpointCapability[] = [
  {
    key: "logical-model-list",
    path: "/entity/v1/entityList",
    priority: "P0",
    role: "search",
    assetTypes: ["LOGICAL_ENTITY"],
    relations: [],
    description: "List logical models.",
    runtime: "design",
  },
  {
    key: "logical-attributes",
    path: "/entity/v1/attributeByEntityId",
    priority: "P0",
    role: "expand",
    assetTypes: ["LOGICAL_ENTITY", "LOGICAL_ATTRIBUTE"],
    relations: ["HAS_ATTRIBUTE"],
    description: "Read the logical attributes declared by a logical model.",
    runtime: "design",
  },
  {
    key: "semantic-backbone",
    path: "/entity/v1/entityColumnRelationById",
    priority: "P0",
    role: "expand",
    assetTypes: [
      "LOGICAL_ENTITY",
      "LOGICAL_ATTRIBUTE",
      "PHYSICAL_TABLE",
      "PHYSICAL_COLUMN",
      "DIMENSION",
      "MEASURE",
      "INDICATOR",
    ],
    relations: [
      "IMPLEMENTED_BY",
      "MAPS_TO",
      "BASED_ON",
      "COMPUTED_FROM",
      "SUPPORTS_DIMENSION",
    ],
    description: "Primary deterministic logical-to-physical and analytical relation source.",
    runtime: "runtime",
  },
  {
    key: "logical-physical-models",
    path: "/entity/v1/phyModelList",
    priority: "P1",
    role: "expand",
    assetTypes: ["LOGICAL_ENTITY", "PHYSICAL_TABLE"],
    relations: ["IMPLEMENTED_BY"],
    description: "Expand a logical model to physical models for a selected source type.",
    runtime: "runtime",
  },
  {
    key: "physical-model-list",
    path: "/table/v1/tableList",
    priority: "P0",
    role: "search",
    assetTypes: ["PHYSICAL_TABLE"],
    relations: [],
    description: "List physical models.",
    runtime: "design",
  },
  {
    key: "physical-model-detail",
    path: "/table/v1/tableById",
    priority: "P0",
    role: "read",
    assetTypes: ["PHYSICAL_TABLE"],
    relations: [],
    description: "Read one physical model.",
    runtime: "design",
  },
  {
    key: "physical-columns",
    path: "/table/v1/columnByTableId",
    priority: "P0",
    role: "expand",
    assetTypes: ["PHYSICAL_TABLE", "PHYSICAL_COLUMN"],
    relations: ["HAS_COLUMN"],
    description: "Expand a physical model to columns.",
    runtime: "design",
  },
  {
    key: "measure-list",
    path: "/measure/v1/measureList",
    priority: "P0",
    role: "search",
    assetTypes: ["MEASURE"],
    relations: [],
    description: "List design-time measures.",
    runtime: "design",
  },
  {
    key: "runtime-measure-list",
    path: "/meta/counters/list",
    priority: "P1",
    role: "search",
    assetTypes: ["MEASURE"],
    relations: [],
    description: "Supplement design-time measures with runtime counters.",
    runtime: "runtime",
  },
  {
    key: "indicator-list",
    path: "/indicator/v1/indicatorList",
    priority: "P0",
    role: "search",
    assetTypes: ["INDICATOR"],
    relations: ["COMPUTED_FROM"],
    description: "List design-time indicators and any returned formulas or measure references.",
    runtime: "design",
  },
  {
    key: "runtime-indicator-list",
    path: "/meta/models/list",
    priority: "P1",
    role: "search",
    assetTypes: ["INDICATOR"],
    relations: [],
    description: "Supplement design-time indicators with runtime indicator models.",
    runtime: "runtime",
  },
  {
    key: "dimension-level-list",
    path: "/meta/levels/list",
    priority: "P0",
    role: "search",
    assetTypes: ["DIMENSION", "DIMENSION_LEVEL"],
    relations: ["HAS_LEVEL"],
    description: "List runtime dimensions and levels.",
    runtime: "runtime",
  },
  {
    key: "dimension-level-detail",
    path: "/meta/levels/{levelId}",
    priority: "P1",
    role: "read",
    assetTypes: ["DIMENSION_LEVEL"],
    relations: [],
    description: "Read one runtime dimension level.",
    runtime: "runtime",
  },
  {
    key: "model-dimension-relation",
    path: "/plat/meta/v1/table/queryDimTable",
    priority: "P1",
    role: "expand",
    assetTypes: ["LOGICAL_ENTITY", "DIMENSION"],
    relations: ["SUPPORTS_DIMENSION"],
    description: "Expand a logical model to supported dimensions.",
    runtime: "runtime",
  },
  {
    key: "dimension-attributes",
    path: "/meta/attribute/list",
    priority: "P1",
    role: "expand",
    assetTypes: ["DIMENSION_LEVEL", "DIMENSION_ATTRIBUTE"],
    relations: ["HAS_ATTRIBUTE"],
    description: "Expand a dimension level to its attributes.",
    runtime: "runtime",
  },
  {
    key: "dimension-rollup",
    path: "/metaone/inner/plat/meta/v1/table/rollUpDimQuery",
    priority: "P1",
    role: "expand",
    assetTypes: ["DIMENSION_LEVEL"],
    relations: ["ROLLS_UP_TO"],
    description: "Expand deterministic dimension roll-up relationships.",
    runtime: "runtime",
  },
  {
    key: "aggregate-model-list",
    path: "/aggregateModel/v1/aggregateModelList",
    priority: "P1",
    role: "search",
    assetTypes: ["AGGREGATE_MODEL", "LOGICAL_ENTITY"],
    relations: ["MAPS_TO"],
    description: "List aggregate models and their logical-model references.",
    runtime: "runtime",
  },
  {
    key: "aggregate-model-sources",
    path: "/aggregateModel/v1/srcPhyModelListByAggregateModel",
    priority: "P1",
    role: "expand",
    assetTypes: ["AGGREGATE_MODEL", "PHYSICAL_TABLE"],
    relations: ["USES"],
    description: "Expand an aggregate model to source physical models.",
    runtime: "design",
  },
  {
    key: "physical-lineage",
    path: "/DataLineage/backendService/lineage/v1/queryByModel",
    priority: "P1",
    role: "expand",
    assetTypes: ["PHYSICAL_TABLE"],
    relations: ["UPSTREAM_OF"],
    description: "Expand physical-model lineage from the lineage service.",
    runtime: "cross-service",
  },
] as const;

export const METAONE_ASSET_TYPES = [
  ...new Set(METAONE_ENDPOINTS.flatMap((endpoint) => endpoint.assetTypes)),
].sort() as AssetType[];

export const METAONE_RELATIONS = [
  ...new Set(METAONE_ENDPOINTS.flatMap((endpoint) => endpoint.relations)),
].sort();
