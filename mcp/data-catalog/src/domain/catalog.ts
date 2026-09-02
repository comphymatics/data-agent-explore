import type {
  Asset,
  AssetType,
  ContextEdge,
  ContextPath,
  MetadataDataset,
  SearchHit,
  SearchInput,
} from "./types.js";

function normalize(value: string): string {
  return value.trim().toLocaleLowerCase().replace(/[\s_-]+/g, "");
}

function tokenize(value: string): string[] {
  return value
    .toLocaleLowerCase()
    .split(/[\s,，。;；/\\|_-]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

export class CatalogIndex {
  readonly assetsById: Map<string, Asset>;
  readonly edgesById: Map<string, ContextEdge>;
  private readonly outgoing = new Map<string, ContextEdge[]>();
  private readonly incoming = new Map<string, ContextEdge[]>();

  constructor(readonly dataset: MetadataDataset) {
    this.assetsById = new Map(dataset.assets.map((item) => [item.id, item]));
    this.edgesById = new Map(dataset.edges.map((item) => [item.id, item]));
    for (const edge of dataset.edges) {
      this.outgoing.set(edge.sourceId, [...(this.outgoing.get(edge.sourceId) ?? []), edge]);
      this.incoming.set(edge.targetId, [...(this.incoming.get(edge.targetId) ?? []), edge]);
    }
  }

  search(input: SearchInput): SearchHit[] {
    const query = input.query.trim();
    const normalizedQuery = normalize(query);
    const queryTokens = tokenize(query);
    const allowedTypes = input.types?.length ? new Set(input.types) : undefined;
    const limit = Math.min(Math.max(input.limit ?? 20, 1), 100);

    return this.dataset.assets
      .filter((asset) => !allowedTypes || allowedTypes.has(asset.type))
      .filter((asset) => !input.domain || normalize(asset.domain) === normalize(input.domain))
      .map((asset) => {
        const matchedBy: string[] = [];
        let score = 0;
        const code = normalize(asset.code);
        const name = normalize(asset.name);
        const aliases = asset.aliases.map(normalize);
        const description = normalize(asset.description);

        if (code === normalizedQuery) {
          score += 1;
          matchedBy.push("exact_code");
        }
        if (name === normalizedQuery) {
          score += 0.95;
          matchedBy.push("exact_name");
        }
        if (aliases.includes(normalizedQuery)) {
          score += 0.9;
          matchedBy.push("exact_alias");
        }
        if (code.includes(normalizedQuery) || name.includes(normalizedQuery)) {
          score += 0.55;
          matchedBy.push("partial_name_or_code");
        }
        const tokenMatches = queryTokens.filter((token) =>
          [asset.code, asset.name, asset.description, ...asset.aliases]
            .join(" ")
            .toLocaleLowerCase()
            .includes(token),
        ).length;
        if (tokenMatches > 0) {
          score += Math.min(0.5, tokenMatches / Math.max(queryTokens.length, 1) / 2);
          matchedBy.push("token");
        }
        if (description.includes(normalizedQuery)) {
          score += 0.2;
          matchedBy.push("description");
        }
        return { asset, score: Math.min(score, 1), matchedBy };
      })
      .filter((hit) => hit.score > 0)
      .sort((a, b) => b.score - a.score || a.asset.id.localeCompare(b.asset.id))
      .slice(0, limit);
  }

  getAsset(id: string): Asset | undefined {
    return this.assetsById.get(id);
  }

  getContext(id: string, depth = 2, maxNodes = 50): {
    focus: Asset;
    nodes: Asset[];
    edges: ContextEdge[];
    truncated: boolean;
  } | undefined {
    const focus = this.assetsById.get(id);
    if (!focus) return undefined;
    const visited = new Set<string>([id]);
    const selectedEdges = new Map<string, ContextEdge>();
    let frontier = [id];
    let truncated = false;

    for (let level = 0; level < Math.min(Math.max(depth, 0), 6); level += 1) {
      const next: string[] = [];
      for (const nodeId of frontier) {
        const edges = [...(this.outgoing.get(nodeId) ?? []), ...(this.incoming.get(nodeId) ?? [])]
          .sort((a, b) => b.confidence - a.confidence);
        for (const edge of edges) {
          const adjacentId = edge.sourceId === nodeId ? edge.targetId : edge.sourceId;
          if (visited.size >= maxNodes && !visited.has(adjacentId)) {
            truncated = true;
            continue;
          }
          selectedEdges.set(edge.id, edge);
          if (!visited.has(adjacentId)) {
            visited.add(adjacentId);
            next.push(adjacentId);
          }
        }
      }
      frontier = next;
      if (!frontier.length) break;
    }

    return {
      focus,
      nodes: [...visited].map((nodeId) => this.assetsById.get(nodeId)).filter((item): item is Asset => Boolean(item)),
      edges: [...selectedEdges.values()],
      truncated,
    };
  }

  expand(
    ids: string[],
    options: { relations?: string[]; limit?: number } = {},
  ): {
    assets: Asset[];
    relations: ContextEdge[];
    truncated: boolean;
  } {
    const sourceIds = new Set(ids);
    const relationFilter = new Set(options.relations ?? []);
    const limit = Math.min(Math.max(options.limit ?? 50, 1), 200);
    const selectedEdges = new Map<string, ContextEdge>();
    const selectedAssets = new Map<string, Asset>();
    for (const id of ids) {
      const focus = this.assetsById.get(id);
      if (focus) selectedAssets.set(id, focus);
      const adjacent = [...(this.outgoing.get(id) ?? []), ...(this.incoming.get(id) ?? [])]
        .filter((edge) => relationFilter.size === 0 || relationFilter.has(edge.predicate))
        .sort((a, b) => b.confidence - a.confidence || a.id.localeCompare(b.id));
      for (const edge of adjacent) {
        selectedEdges.set(edge.id, edge);
        const relatedId = sourceIds.has(edge.sourceId) ? edge.targetId : edge.sourceId;
        const related = this.assetsById.get(relatedId);
        if (related) selectedAssets.set(related.id, related);
      }
    }
    const truncated = selectedAssets.size > limit;
    const assets = [...selectedAssets.values()].slice(0, limit);
    const allowedIds = new Set(assets.map((asset) => asset.id));
    return {
      assets,
      relations: [...selectedEdges.values()].filter(
        (edge) => allowedIds.has(edge.sourceId) && allowedIds.has(edge.targetId),
      ),
      truncated,
    };
  }

  findPaths(
    fromId: string,
    options: { toId?: string; targetTypes?: AssetType[]; maxDepth?: number; limit?: number },
  ): ContextPath[] {
    if (!this.assetsById.has(fromId)) return [];
    const maxDepth = Math.min(Math.max(options.maxDepth ?? 5, 1), 8);
    const limit = Math.min(Math.max(options.limit ?? 10, 1), 50);
    const targetTypes = new Set(options.targetTypes ?? []);
    const queue: Array<{ nodeIds: string[]; edges: ContextEdge[] }> = [{ nodeIds: [fromId], edges: [] }];
    const results: ContextPath[] = [];

    while (queue.length && results.length < limit) {
      const current = queue.shift()!;
      const currentId = current.nodeIds[current.nodeIds.length - 1]!;
      if (current.edges.length > 0) {
        const currentAsset = this.assetsById.get(currentId)!;
        const isTarget = options.toId
          ? currentId === options.toId
          : targetTypes.size > 0 && targetTypes.has(currentAsset.type);
        if (isTarget) {
          const inferredCount = current.edges.filter((item) => item.assertionType === "inferred").length;
          const confidence = current.edges.reduce((sum, item) => sum + item.confidence, 0) / current.edges.length;
          results.push({
            nodes: current.nodeIds.map((id) => this.assetsById.get(id)!),
            edges: current.edges,
            score: Number((confidence - inferredCount * 0.1 - current.edges.length * 0.01).toFixed(4)),
          });
          continue;
        }
      }
      if (current.edges.length >= maxDepth) continue;

      const adjacent = [...(this.outgoing.get(currentId) ?? []), ...(this.incoming.get(currentId) ?? [])]
        .sort((a, b) => b.confidence - a.confidence);
      for (const candidate of adjacent) {
        const nextId = candidate.sourceId === currentId ? candidate.targetId : candidate.sourceId;
        if (current.nodeIds.includes(nextId)) continue;
        queue.push({ nodeIds: [...current.nodeIds, nextId], edges: [...current.edges, candidate] });
      }
    }

    return results.sort((a, b) => b.score - a.score || a.edges.length - b.edges.length);
  }

  evidenceFor(edgeId: string) {
    const edge = this.edgesById.get(edgeId);
    if (!edge) return undefined;
    const evidenceById = new Map(this.dataset.evidence.map((item) => [item.id, item]));
    return {
      edge,
      source: this.assetsById.get(edge.sourceId),
      target: this.assetsById.get(edge.targetId),
      evidence: edge.evidenceRefs.map((id) => evidenceById.get(id)).filter(Boolean),
      indexVersion: this.dataset.version,
    };
  }
}
