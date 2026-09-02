import { readFile } from "node:fs/promises";
import type { ContextGraph, ParsedDocument } from "./schema.js";
import { ExtractionAccumulator } from "./accumulator.js";
import { extractDocument, linkSemanticCandidates } from "./extractors.js";
import { parserFor } from "./parsers/parser.js";
import { sha256 } from "./utils.js";

export interface BuildOptions {
  sourceVersion?: string;
  now?: () => Date;
}

export class ContextBuilder {
  constructor(private readonly options: BuildOptions = {}) {}

  async parse(paths: string[]): Promise<ParsedDocument[]> {
    const documents: ParsedDocument[] = [];
    for (const path of [...new Set(paths)].sort()) {
      const document = await parserFor(path).parse(path);
      if (this.options.sourceVersion) document.sourceVersion = this.options.sourceVersion;
      documents.push(document);
    }
    return documents;
  }

  buildFromParsed(documents: ParsedDocument[]): ContextGraph {
    const accumulator = new ExtractionAccumulator();
    for (const document of documents) extractDocument(document, accumulator);
    linkSemanticCandidates(accumulator);
    const entities = accumulator.entities().sort((left, right) => left.entityId.localeCompare(right.entityId));
    const facts = accumulator.facts().sort((left, right) => left.factId.localeCompare(right.factId));
    const evidence = accumulator.evidence().sort((left, right) => left.evidenceId.localeCompare(right.evidenceId));
    const versionMaterial = JSON.stringify({
      documents: documents.map((document) => [document.documentId, document.contentHash]).sort(),
      entities: entities.map((entity) => entity.entityId),
      facts: facts.map((fact) => [fact.factId, fact.assertionType, fact.confidence]),
    });
    return {
      schemaVersion: "0.1",
      indexVersion: `context-v0.1-${sha256(versionMaterial).slice(0, 12)}`,
      generatedAt: (this.options.now?.() ?? new Date()).toISOString(),
      documents: documents.map((document) => ({
        documentId: document.documentId,
        name: document.name,
        sourceUri: document.sourceUri,
        sourceType: document.sourceType,
        sourceVersion: document.sourceVersion,
        contentHash: document.contentHash,
        blockCount: document.blocks.length,
      })),
      entities,
      facts,
      evidence,
      warnings: documents.flatMap((document) => document.warnings.map((warning) => `${document.name}: ${warning}`)),
    };
  }

  async build(paths: string[]): Promise<ContextGraph> {
    return this.buildFromParsed(await this.parse(paths));
  }
}

export async function loadContextGraph(path: string): Promise<ContextGraph> {
  return JSON.parse(await readFile(path, "utf8")) as ContextGraph;
}
