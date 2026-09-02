import { createHash } from "node:crypto";
import { basename } from "node:path";
import type { SourceType } from "./schema.js";

export const EXTRACTOR_VERSION = "explore-context-builder/0.1.0";

export function sha256(value: string | Buffer): string {
  return createHash("sha256").update(value).digest("hex");
}

export function stableId(prefix: string, ...parts: Array<string | number | undefined>): string {
  const material = parts.filter((part) => part !== undefined).join("\u001f");
  return `${prefix}:${sha256(material).slice(0, 20)}`;
}

export function normalize(value: string): string {
  return value.trim().toLocaleLowerCase().replace(/[\s_\-–—/\\|:：()（）\[\]【】]+/g, "");
}

export function normalizeCode(value: string): string {
  return value.trim().replace(/\s+/g, "_").toLocaleUpperCase();
}

export function compact(value: string): string {
  return value.replace(/\s+/g, " ").trim();
}

export function unique<T>(values: T[]): T[] {
  return [...new Set(values)];
}

export function classifySource(path: string): SourceType {
  const name = basename(path).toLocaleLowerCase();
  if (/资产目录|model.asset.catalog|datacube-model-asset/.test(name)) return "MODEL_CATALOG";
  if (/数据字典|data.dictionary/.test(name)) return "DATA_DICTIONARY";
  if (/建模文档|kpi|kqi|modeling-document/.test(name)) return "KPI_DEFINITION";
  if (/售前|专题|usecase|use-case|metro/.test(name)) return "USE_CASE_SPECIFICATION";
  if (/etl|dataflow|数据流/.test(name)) return "ETL_SPECIFICATION";
  return "UNKNOWN";
}

export function cellText(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return compact(String(value));
  }
  if (value instanceof Date) return value.toISOString();
  if (typeof value === "object") {
    const record = value as Record<string, unknown>;
    if (Array.isArray(record.richText)) {
      return compact(
        record.richText
          .map((part) => (part && typeof part === "object" ? String((part as Record<string, unknown>).text ?? "") : ""))
          .join(""),
      );
    }
    if (record.result !== undefined) return cellText(record.result);
    if (record.text !== undefined) return cellText(record.text);
    if (record.hyperlink !== undefined) return cellText(record.hyperlink);
  }
  return compact(String(value));
}
