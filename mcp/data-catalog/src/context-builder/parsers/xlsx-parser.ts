import { readFile } from "node:fs/promises";
import { basename } from "node:path";
import ExcelJS from "exceljs";
import type { DocumentParser } from "./parser.js";
import type { ParsedBlock, ParsedDocument } from "../schema.js";
import { cellText, classifySource, sha256, stableId } from "../utils.js";

export class XlsxDocumentParser implements DocumentParser {
  supports(path: string): boolean {
    return /\.xlsx$/i.test(path);
  }

  async parse(path: string): Promise<ParsedDocument> {
    const source = await readFile(path);
    const workbook = new ExcelJS.Workbook();
    await workbook.xlsx.load(source as unknown as ExcelJS.Buffer);
    const blocks: ParsedBlock[] = [];

    for (const sheet of workbook.worksheets) {
      let headers: string[] | undefined;
      sheet.eachRow({ includeEmpty: false }, (row, rowNumber) => {
        const cells = Array.from({ length: Math.max(sheet.columnCount, row.cellCount) }, (_, offset) =>
          cellText(row.getCell(offset + 1).value),
        );
        if (!headers) headers = cells;
        blocks.push({
          kind: "table_row",
          text: cells.filter(Boolean).join(" | "),
          headers,
          cells,
          sectionPath: [sheet.name],
          location: { kind: "sheet_row", sheet: sheet.name, row: rowNumber, section: sheet.name },
        });
      });
    }

    const name = basename(path);
    return {
      documentId: stableId("doc", name, sha256(source)),
      name,
      sourceUri: path,
      sourceType: classifySource(path),
      contentHash: sha256(source),
      blocks,
      warnings: [],
    };
  }
}
