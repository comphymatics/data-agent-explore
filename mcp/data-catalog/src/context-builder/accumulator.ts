import type {
  AssertionType,
  Entity,
  EntityType,
  Evidence,
  Fact,
  ParsedBlock,
  ParsedDocument,
} from "./schema.js";
import { EXTRACTOR_VERSION, normalize, normalizeCode, sha256, stableId, unique } from "./utils.js";

const entityPrefixes: Record<EntityType, string> = {
  PHYSICAL_MODEL: "pm",
  PHYSICAL_FIELD: "pf",
  LOGICAL_MODEL: "lm",
  BUSINESS_CONCEPT: "bc",
  NETWORK_PROCEDURE: "np",
  USE_CASE: "uc",
  ANALYSIS_CAPABILITY: "cap",
  DATA_REQUIREMENT: "req",
  DIMENSION: "dim",
  MEASURE: "measure",
  COUNTER: "counter",
  KPI: "kpi",
  KQI: "kqi",
  FORMULA: "formula",
  RULE: "rule",
  CONSTRAINT: "constraint",
  APPLICATION: "app",
  DATA_SOURCE: "source",
};

function readableKey(value: string): string {
  const candidate = value.trim().toLocaleLowerCase().replace(/\s+/g, "_");
  return /^[a-z0-9_.-]+$/.test(candidate) ? candidate : stableId("n", normalize(value)).slice(2);
}

function assertionRank(value: AssertionType): number {
  return { CANDIDATE: 0, INFERRED: 1, DERIVED: 2, EXPLICIT: 3 }[value];
}

export interface EntityInput {
  entityType: EntityType;
  name: string;
  code?: string;
  aliases?: string[];
  description?: string;
  properties?: Record<string, unknown>;
  evidenceIds?: string[];
  idHint?: string;
}

export interface FactInput {
  subjectId: string;
  predicate: string;
  objectId: string;
  qualifiers?: Record<string, unknown>;
  assertionType: AssertionType;
  confidence: number;
  evidenceIds: string[];
}

export class ExtractionAccumulator {
  private readonly entitiesByKey = new Map<string, Entity>();
  private readonly entitiesById = new Map<string, Entity>();
  private readonly factsByKey = new Map<string, Fact>();
  private readonly evidenceById = new Map<string, Evidence>();

  addEvidence(document: ParsedDocument, block: ParsedBlock, confidence: number): Evidence {
    const locationKey = JSON.stringify(block.location);
    const evidenceId = stableId("ev", document.documentId, locationKey, block.text);
    const existing = this.evidenceById.get(evidenceId);
    if (existing) return existing;
    const evidence: Evidence = {
      evidenceId,
      documentId: document.documentId,
      documentName: document.name,
      sourceType: document.sourceType,
      sourceUri: document.sourceUri,
      sourceVersion: document.sourceVersion,
      location: block.location,
      rawText: block.text,
      contentHash: sha256(block.text),
      extractorVersion: EXTRACTOR_VERSION,
      confidence,
    };
    this.evidenceById.set(evidenceId, evidence);
    return evidence;
  }

  addEntity(input: EntityInput): Entity {
    const identity = normalize(input.code || input.name);
    const key = `${input.entityType}:${identity}`;
    const existing = this.entitiesByKey.get(key);
    if (existing) {
      existing.aliases = unique([...existing.aliases, ...(input.aliases ?? [])].filter(Boolean));
      existing.description = existing.description || input.description || "";
      existing.properties = { ...existing.properties, ...(input.properties ?? {}) };
      existing.evidenceIds = unique([...existing.evidenceIds, ...(input.evidenceIds ?? [])]);
      return existing;
    }
    const entityId =
      input.idHint ?? `${entityPrefixes[input.entityType]}:smartcare:${readableKey(input.code || input.name)}`;
    const entity: Entity = {
      entityId,
      entityType: input.entityType,
      name: input.name.trim(),
      code: input.code ? normalizeCode(input.code) : undefined,
      aliases: unique((input.aliases ?? []).map((value) => value.trim()).filter(Boolean)),
      description: input.description?.trim() ?? "",
      properties: input.properties ?? {},
      evidenceIds: unique(input.evidenceIds ?? []),
      version: "0.1",
    };
    this.entitiesByKey.set(key, entity);
    this.entitiesById.set(entity.entityId, entity);
    return entity;
  }

  addFact(input: FactInput): Fact {
    if (!this.entitiesById.has(input.subjectId) || !this.entitiesById.has(input.objectId)) {
      throw new Error(`fact endpoints must exist: ${input.subjectId} ${input.predicate} ${input.objectId}`);
    }
    const qualifiers = input.qualifiers ?? {};
    const key = `${input.subjectId}\u001f${input.predicate}\u001f${input.objectId}\u001f${JSON.stringify(qualifiers)}`;
    const existing = this.factsByKey.get(key);
    if (existing) {
      existing.evidenceIds = unique([...existing.evidenceIds, ...input.evidenceIds]);
      existing.confidence = Math.max(existing.confidence, input.confidence);
      if (assertionRank(input.assertionType) > assertionRank(existing.assertionType)) {
        existing.assertionType = input.assertionType;
      }
      existing.status = existing.assertionType === "EXPLICIT" || existing.assertionType === "DERIVED" ? "VERIFIED" : "CANDIDATE";
      return existing;
    }
    const fact: Fact = {
      factId: stableId("fact", key),
      subjectId: input.subjectId,
      predicate: input.predicate,
      objectId: input.objectId,
      qualifiers,
      assertionType: input.assertionType,
      confidence: Math.max(0, Math.min(1, input.confidence)),
      evidenceIds: unique(input.evidenceIds),
      status: input.assertionType === "EXPLICIT" || input.assertionType === "DERIVED" ? "VERIFIED" : "CANDIDATE",
    };
    this.factsByKey.set(key, fact);
    return fact;
  }

  getEntity(id: string): Entity | undefined {
    return this.entitiesById.get(id);
  }

  entities(): Entity[] {
    return [...this.entitiesById.values()];
  }

  facts(): Fact[] {
    return [...this.factsByKey.values()];
  }

  evidence(): Evidence[] {
    return [...this.evidenceById.values()];
  }
}
