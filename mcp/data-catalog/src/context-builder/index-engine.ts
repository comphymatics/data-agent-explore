import type { ContextPath, EntityType, SearchHit, SearchInput } from "./schema.js";
import type { ContextRepository } from "./store.js";
import { normalize, unique } from "./utils.js";

function tokenize(value: string): string[] {
  const normalized = value.toLocaleLowerCase();
  const latin = normalized.split(/[^a-z0-9_.-]+/).filter((token) => token.length >= 2);
  const chinese = [...normalized.matchAll(/[\u4e00-\u9fff]{2,}/g)].flatMap((match) => {
    const term = match[0];
    return term.length <= 4 ? [term] : [term, ...Array.from({ length: term.length - 1 }, (_, index) => term.slice(index, index + 2))];
  });
  return unique([...latin, ...chinese]);
}

export class ContextIndexEngine {
  private readonly outgoing = new Map<string, string[]>();
  private readonly incoming = new Map<string, string[]>();

  constructor(readonly repository: ContextRepository) {
    for (const fact of repository.listFacts()) {
      this.outgoing.set(fact.subjectId, [...(this.outgoing.get(fact.subjectId) ?? []), fact.factId]);
      this.incoming.set(fact.objectId, [...(this.incoming.get(fact.objectId) ?? []), fact.factId]);
    }
  }

  search(input: SearchInput): SearchHit[] {
    const query = input.query.trim();
    const normalizedQuery = normalize(query);
    const queryTokens = tokenize(query);
    const allowedTypes = input.entityTypes?.length ? new Set(input.entityTypes) : undefined;
    const limit = Math.min(Math.max(input.limit ?? 20, 1), 100);
    return this.repository
      .listEntities()
      .filter((entity) => !allowedTypes || allowedTypes.has(entity.entityType))
      .filter((entity) =>
        Object.entries(input.filters ?? {}).every(([key, value]) => normalize(String(entity.properties[key] ?? "")) === normalize(value)),
      )
      .map((entity) => {
        const matchedBy: string[] = [];
        let score = 0;
        const code = normalize(entity.code ?? "");
        const name = normalize(entity.name);
        const aliases = entity.aliases.map(normalize);
        const haystack = [entity.code, entity.name, entity.description, ...entity.aliases, ...Object.values(entity.properties)]
          .filter((value) => typeof value === "string")
          .join(" ")
          .toLocaleLowerCase();
        if (code && code === normalizedQuery) { score += 1; matchedBy.push("exact_code"); }
        if (name === normalizedQuery) { score += 0.95; matchedBy.push("exact_name"); }
        if (aliases.includes(normalizedQuery)) { score += 0.9; matchedBy.push("exact_alias"); }
        const codePartial = code.length >= 2 && (code.includes(normalizedQuery) || normalizedQuery.includes(code));
        const namePartial = name.length >= 2 && (name.includes(normalizedQuery) || normalizedQuery.includes(name));
        if (normalizedQuery.length >= 2 && (codePartial || namePartial)) {
          score += 0.55;
          matchedBy.push("partial_name_or_code");
        }
        const tokenMatches = queryTokens.filter((token) => haystack.includes(token)).length;
        if (tokenMatches) {
          score += Math.min(0.45, (tokenMatches / Math.max(queryTokens.length, 1)) * 0.45);
          matchedBy.push("lexical_token");
        }
        return { entity, score: Math.min(Number(score.toFixed(4)), 1), matchedBy };
      })
      .filter((hit) => hit.score > 0)
      .sort((left, right) => right.score - left.score || left.entity.entityId.localeCompare(right.entity.entityId))
      .slice(0, limit);
  }

  definition(entityId: string) {
    const entity = this.repository.getEntity(entityId);
    if (!entity) return undefined;
    const facts = this.repository.factsForEntity(entityId);
    const evidenceIds = unique([...entity.evidenceIds, ...facts.flatMap((fact) => fact.evidenceIds)]);
    return {
      entity,
      facts,
      evidence: evidenceIds.map((id) => this.repository.getEvidence(id)).filter(Boolean),
      indexVersion: this.repository.graph.indexVersion,
    };
  }

  trace(
    sourceId: string,
    options: { targetId?: string; targetTypes?: EntityType[]; maxDepth?: number; limit?: number; includeCandidates?: boolean },
  ): ContextPath[] {
    if (!this.repository.getEntity(sourceId)) return [];
    const maxDepth = Math.min(Math.max(options.maxDepth ?? 5, 1), 8);
    const limit = Math.min(Math.max(options.limit ?? 10, 1), 50);
    const targetTypes = new Set(options.targetTypes ?? []);
    const includeCandidates = options.includeCandidates ?? true;
    const queue: Array<{ entityIds: string[]; factIds: string[] }> = [{ entityIds: [sourceId], factIds: [] }];
    const results: ContextPath[] = [];

    while (queue.length && results.length < limit) {
      const current = queue.shift()!;
      const currentId = current.entityIds.at(-1)!;
      if (current.factIds.length) {
        const currentEntity = this.repository.getEntity(currentId)!;
        const reached = options.targetId ? currentId === options.targetId : targetTypes.has(currentEntity.entityType);
        if (reached) {
          const facts = current.factIds.map((id) => this.repository.getFact(id)!);
          const confidence = facts.reduce((minimum, fact) => Math.min(minimum, fact.confidence), 1);
          results.push({
            entities: current.entityIds.map((id) => this.repository.getEntity(id)!),
            facts,
            confidence: Number(confidence.toFixed(4)),
          });
          continue;
        }
      }
      if (current.factIds.length >= maxDepth) continue;
      const factIds = unique([...(this.outgoing.get(currentId) ?? []), ...(this.incoming.get(currentId) ?? [])]);
      const adjacent = factIds
        .map((id) => this.repository.getFact(id)!)
        .filter((fact) => includeCandidates || fact.status === "VERIFIED")
        .sort((left, right) => right.confidence - left.confidence || left.factId.localeCompare(right.factId));
      for (const fact of adjacent) {
        const nextId = fact.subjectId === currentId ? fact.objectId : fact.subjectId;
        if (current.entityIds.includes(nextId)) continue;
        queue.push({ entityIds: [...current.entityIds, nextId], factIds: [...current.factIds, fact.factId] });
      }
    }
    return results.sort((left, right) => right.confidence - left.confidence || left.facts.length - right.facts.length);
  }
}
