import { readFile } from "node:fs/promises";
import { basename } from "node:path";
import mammoth from "mammoth";
import { parse } from "node-html-parser";
import type { HTMLElement } from "node-html-parser";
import type { DocumentParser } from "./parser.js";
import type { ParsedBlock, ParsedDocument } from "../schema.js";
import { classifySource, compact, sha256, stableId } from "../utils.js";

function tableGrid(table: HTMLElement): string[][] {
  const activeSpans = new Map<number, { value: string; remaining: number }>();
  const result: string[][] = [];
  for (const row of table.querySelectorAll("tr")) {
    const values: string[] = [];
    let column = 0;
    const consumeSpans = () => {
      while (activeSpans.has(column)) {
        const span = activeSpans.get(column)!;
        values[column] = span.value;
        span.remaining -= 1;
        if (span.remaining <= 0) activeSpans.delete(column);
        column += 1;
      }
    };
    for (const cell of row.querySelectorAll("th,td")) {
      consumeSpans();
      const value = compact(cell.text);
      const columnSpan = Math.max(Number(cell.getAttribute("colspan") ?? 1), 1);
      const rowSpan = Math.max(Number(cell.getAttribute("rowspan") ?? 1), 1);
      for (let offset = 0; offset < columnSpan; offset += 1) {
        values[column + offset] = value;
        if (rowSpan > 1) activeSpans.set(column + offset, { value, remaining: rowSpan - 1 });
      }
      column += columnSpan;
    }
    consumeSpans();
    result.push(values.map((value) => value ?? ""));
  }
  return result;
}

export class DocxDocumentParser implements DocumentParser {
  supports(path: string): boolean {
    return /\.docx$/i.test(path);
  }

  async parse(path: string): Promise<ParsedDocument> {
    const source = await readFile(path);
    const result = await mammoth.convertToHtml({ buffer: source });
    const root = parse(result.value);
    const blocks: ParsedBlock[] = [];
    const sectionPath: string[] = [];
    let tableNumber = 0;
    let paragraphNumber = 0;

    for (const child of root.childNodes) {
      if (child.nodeType !== 1) continue;
      const element = child as HTMLElement;
      const tag = element.rawTagName.toLocaleLowerCase();
      const heading = tag.match(/^h([1-6])$/);
      if (heading) {
        const level = Number(heading[1]);
        const title = compact(element.text);
        sectionPath.length = level - 1;
        sectionPath[level - 1] = title;
        blocks.push({
          kind: "heading",
          text: title,
          headingLevel: level,
          sectionPath: [...sectionPath],
          location: { kind: "docx_block", section: sectionPath.join(" > "), paragraph: ++paragraphNumber },
        });
        continue;
      }
      if (tag === "table") {
        tableNumber += 1;
        const rows = tableGrid(element);
        const headers = rows[0] ?? [];
        rows.slice(1).forEach((cells, offset) => {
          blocks.push({
            kind: "table_row",
            text: cells.join(" | "),
            headers,
            cells,
            sectionPath: [...sectionPath],
            location: {
              kind: "docx_block",
              section: sectionPath.join(" > "),
              table: tableNumber,
              row: offset + 2,
            },
          });
        });
        continue;
      }
      if (tag === "ul" || tag === "ol") {
        for (const item of element.querySelectorAll("li")) {
          blocks.push({
            kind: "list_item",
            text: compact(item.text),
            sectionPath: [...sectionPath],
            location: { kind: "docx_block", section: sectionPath.join(" > "), paragraph: ++paragraphNumber },
          });
        }
        continue;
      }
      if (tag === "p" && compact(element.text)) {
        blocks.push({
          kind: "paragraph",
          text: compact(element.text),
          sectionPath: [...sectionPath],
          location: { kind: "docx_block", section: sectionPath.join(" > "), paragraph: ++paragraphNumber },
        });
      }
    }

    const name = basename(path);
    return {
      documentId: stableId("doc", name, sha256(source)),
      name,
      sourceUri: path,
      sourceType: classifySource(path),
      contentHash: sha256(source),
      blocks,
      warnings: result.messages.map((message) => `${message.type}: ${message.message}`),
    };
  }
}
