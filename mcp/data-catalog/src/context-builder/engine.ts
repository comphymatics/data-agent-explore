import { loadContextGraph } from "./builder.js";
import { ContextIndexEngine } from "./index-engine.js";
import type { ContextGraph, EntityType, SearchInput } from "./schema.js";
import { InMemoryContextStore } from "./store.js";

export class OfflineContextEngine {
  readonly store: InMemoryContextStore;
  readonly index: ContextIndexEngine;

  constructor(readonly graph: ContextGraph) {
    this.store = new InMemoryContextStore(graph);
    this.index = new ContextIndexEngine(this.store);
  }

  static async fromFile(path: string): Promise<OfflineContextEngine> {
    return new OfflineContextEngine(await loadContextGraph(path));
  }

  dataFind(input: SearchInput) {
    return {
      records: this.index.search(input),
      indexVersion: this.graph.indexVersion,
    };
  }

  dataDefinition(entityId: string) {
    const definition = this.index.definition(entityId);
    return {
      definition: definition ?? null,
      indexVersion: this.graph.indexVersion,
      warnings: definition ? [] : [`entity not found: ${entityId}`],
    };
  }

  dataTrace(
    sourceId: string,
    options: {
      targetId?: string;
      targetTypes?: EntityType[];
      maxDepth?: number;
      limit?: number;
      includeCandidates?: boolean;
    },
  ) {
    const source = this.store.getEntity(sourceId);
    return {
      paths: source ? this.index.trace(sourceId, options) : [],
      indexVersion: this.graph.indexVersion,
      warnings: source ? [] : [`entity not found: ${sourceId}`],
    };
  }
}
