export type AssetType =
  | "PHYSICAL_TABLE"
  | "PHYSICAL_COLUMN"
  | "LOGICAL_ENTITY"
  | "LOGICAL_ATTRIBUTE"
  | "AGGREGATE_MODEL"
  | "CATALOG"
  | "SID_ABE"
  | "SID_BE"
  | "DIMENSION"
  | "DIMENSION_HIERARCHY"
  | "DIMENSION_LEVEL"
  | "DIMENSION_ATTRIBUTE"
  | "MEASURE"
  | "INDICATOR"
  | "INDICATOR_VARIABLE"
  | "DATA_FLOW"
  | "ANALYSIS_PURPOSE";

export type AssertionType =
  | "explicit"
  | "derived"
  | "inferred"
  | "user_confirmed";

export interface Evidence {
  id: string;
  sourceType: "metadata_api" | "standard" | "business_definition" | "inference";
  sourceUri: string;
  capturedAt: string;
  description: string;
}

export interface Asset {
  id: string;
  type: AssetType;
  code: string;
  name: string;
  description: string;
  aliases: string[];
  domain: string;
  attributes: Record<string, unknown>;
  evidenceRefs: string[];
}

export interface ContextEdge {
  id: string;
  sourceId: string;
  predicate:
    | "HAS_COLUMN"
    | "IMPLEMENTS"
    | "IMPLEMENTED_BY"
    | "ALIGNS_WITH"
    | "BELONGS_TO"
    | "BASED_ON"
    | "ANALYZED_BY"
    | "USES"
    | "ABOUT"
    | "SUPPORTED_BY"
    | "DERIVED_FROM"
    | "HAS_ATTRIBUTE"
    | "MAPS_TO"
    | "SUPPORTS_DIMENSION"
    | "HAS_LEVEL"
    | "ROLLS_UP_TO"
    | "UPSTREAM_OF"
    | "HAS_CHILD"
    | "HAS_HIERARCHY"
    | "USES_DIMENSION"
    | "MAPS_TO_LEVEL"
    | "RELATED_TO"
    | "RELATED_LEVEL"
    | "PROVIDES_MEASURE"
    | "AVAILABLE_BY"
    | "CALCULATED_FROM"
    | "USES_VARIABLE"
    | "ASSOCIATED_WITH"
    | "REFERENCES"
    | "DRILL_DOWN"
    | "ABNORMAL_DRILL"
    | "DERIVES_TO"
    | "TRANSFORMED_BY"
    | "SOURCE_MODEL"
    | "BELONGS_TO_CATALOG";
  targetId: string;
  assertionType: AssertionType;
  confidence: number;
  status: "candidate" | "verified";
  evidenceRefs: string[];
}

export interface MetadataDataset {
  version: string;
  generatedAt: string;
  assets: Asset[];
  edges: ContextEdge[];
  evidence: Evidence[];
}

export interface SearchInput {
  query: string;
  types?: AssetType[];
  domain?: string;
  limit?: number;
  cursor?: string;
}

export interface ExpandInput {
  ids: string[];
  relations?: string[];
  limit?: number;
}

export interface SearchHit {
  asset: Asset;
  score: number;
  matchedBy: string[];
}

export interface ContextPath {
  nodes: Asset[];
  edges: ContextEdge[];
  score: number;
}
