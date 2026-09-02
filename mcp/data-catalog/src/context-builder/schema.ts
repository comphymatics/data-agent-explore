export const ENTITY_TYPES = [
  "PHYSICAL_MODEL",
  "PHYSICAL_FIELD",
  "LOGICAL_MODEL",
  "BUSINESS_CONCEPT",
  "NETWORK_PROCEDURE",
  "USE_CASE",
  "ANALYSIS_CAPABILITY",
  "DATA_REQUIREMENT",
  "DIMENSION",
  "MEASURE",
  "COUNTER",
  "KPI",
  "KQI",
  "FORMULA",
  "RULE",
  "CONSTRAINT",
  "APPLICATION",
  "DATA_SOURCE",
] as const;

export type EntityType = (typeof ENTITY_TYPES)[number];
export type AssertionType = "EXPLICIT" | "DERIVED" | "INFERRED" | "CANDIDATE";
export type FactStatus = "VERIFIED" | "CANDIDATE";
export type SourceType =
  | "MODEL_CATALOG"
  | "DATA_DICTIONARY"
  | "KPI_DEFINITION"
  | "USE_CASE_SPECIFICATION"
  | "ETL_SPECIFICATION"
  | "UNKNOWN";

export interface SourceLocation {
  kind: "sheet_row" | "docx_block";
  sheet?: string;
  row?: number;
  section?: string;
  table?: number;
  paragraph?: number;
  lineStart?: number;
  lineEnd?: number;
}

export interface Evidence {
  evidenceId: string;
  documentId: string;
  documentName: string;
  sourceType: SourceType;
  sourceUri: string;
  sourceVersion?: string;
  location: SourceLocation;
  rawText: string;
  contentHash: string;
  extractorVersion: string;
  confidence: number;
}

export interface Entity {
  entityId: string;
  entityType: EntityType;
  name: string;
  code?: string;
  aliases: string[];
  description: string;
  properties: Record<string, unknown>;
  evidenceIds: string[];
  version: string;
}

export interface Fact {
  factId: string;
  subjectId: string;
  predicate: string;
  objectId: string;
  qualifiers: Record<string, unknown>;
  assertionType: AssertionType;
  confidence: number;
  evidenceIds: string[];
  status: FactStatus;
}

export interface ParsedBlock {
  kind: "heading" | "paragraph" | "list_item" | "table_row";
  text: string;
  location: SourceLocation;
  headingLevel?: number;
  sectionPath: string[];
  headers?: string[];
  cells?: string[];
}

export interface ParsedDocument {
  documentId: string;
  name: string;
  sourceUri: string;
  sourceType: SourceType;
  sourceVersion?: string;
  contentHash: string;
  blocks: ParsedBlock[];
  warnings: string[];
}

export interface SourceDocumentSummary {
  documentId: string;
  name: string;
  sourceUri: string;
  sourceType: SourceType;
  sourceVersion?: string;
  contentHash: string;
  blockCount: number;
}

export interface ContextGraph {
  schemaVersion: "0.1";
  indexVersion: string;
  generatedAt: string;
  documents: SourceDocumentSummary[];
  entities: Entity[];
  facts: Fact[];
  evidence: Evidence[];
  warnings: string[];
}

export interface SearchInput {
  query: string;
  entityTypes?: EntityType[];
  filters?: Record<string, string>;
  limit?: number;
}

export interface SearchHit {
  entity: Entity;
  score: number;
  matchedBy: string[];
}

export interface ContextPath {
  entities: Entity[];
  facts: Fact[];
  confidence: number;
}
