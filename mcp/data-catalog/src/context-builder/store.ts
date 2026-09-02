import type { ContextGraph, Entity, Evidence, Fact } from "./schema.js";

export interface EntityRepository {
  getEntity(id: string): Entity | undefined;
  listEntities(): Entity[];
}

export interface FactRepository {
  getFact(id: string): Fact | undefined;
  listFacts(): Fact[];
  factsForEntity(id: string): Fact[];
}

export interface EvidenceRepository {
  getEvidence(id: string): Evidence | undefined;
  listEvidence(): Evidence[];
}

export interface ContextRepository extends EntityRepository, FactRepository, EvidenceRepository {
  readonly graph: ContextGraph;
}

export class InMemoryContextStore implements ContextRepository {
  private readonly entitiesById: Map<string, Entity>;
  private readonly factsById: Map<string, Fact>;
  private readonly evidenceById: Map<string, Evidence>;
  private readonly factsByEntity = new Map<string, Fact[]>();

  constructor(readonly graph: ContextGraph) {
    this.entitiesById = new Map(graph.entities.map((entity) => [entity.entityId, entity]));
    this.factsById = new Map(graph.facts.map((fact) => [fact.factId, fact]));
    this.evidenceById = new Map(graph.evidence.map((evidence) => [evidence.evidenceId, evidence]));
    for (const fact of graph.facts) {
      if (!this.entitiesById.has(fact.subjectId) || !this.entitiesById.has(fact.objectId)) {
        throw new Error(`context graph contains a dangling fact: ${fact.factId}`);
      }
      for (const evidenceId of fact.evidenceIds) {
        if (!this.evidenceById.has(evidenceId)) throw new Error(`fact ${fact.factId} references missing evidence ${evidenceId}`);
      }
      this.factsByEntity.set(fact.subjectId, [...(this.factsByEntity.get(fact.subjectId) ?? []), fact]);
      this.factsByEntity.set(fact.objectId, [...(this.factsByEntity.get(fact.objectId) ?? []), fact]);
    }
  }

  getEntity(id: string): Entity | undefined { return this.entitiesById.get(id); }
  listEntities(): Entity[] { return [...this.entitiesById.values()]; }
  getFact(id: string): Fact | undefined { return this.factsById.get(id); }
  listFacts(): Fact[] { return [...this.factsById.values()]; }
  factsForEntity(id: string): Fact[] { return [...(this.factsByEntity.get(id) ?? [])]; }
  getEvidence(id: string): Evidence | undefined { return this.evidenceById.get(id); }
  listEvidence(): Evidence[] { return [...this.evidenceById.values()]; }
}
