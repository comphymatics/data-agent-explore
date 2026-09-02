import { extname } from "node:path";
import type { ParsedDocument } from "../schema.js";
import { DocxDocumentParser } from "./docx-parser.js";
import { XlsxDocumentParser } from "./xlsx-parser.js";

export interface DocumentParser {
  supports(path: string): boolean;
  parse(path: string): Promise<ParsedDocument>;
}

const parsers: DocumentParser[] = [
  new XlsxDocumentParser(),
  new DocxDocumentParser(),
];

export function parserFor(path: string): DocumentParser {
  const parser = parsers.find((candidate) => candidate.supports(path));
  if (!parser) throw new Error(`unsupported document format: ${extname(path) || path}`);
  return parser;
}

export const supportedExtensions = new Set([".xlsx", ".docx"]);
