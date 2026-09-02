import type { Entity, ParsedBlock, ParsedDocument } from "./schema.js";
import { ExtractionAccumulator } from "./accumulator.js";
import { compact, normalize, unique } from "./utils.js";

function rowRecord(block: ParsedBlock): Record<string, string> {
  const headers = block.headers ?? [];
  const cells = block.cells ?? [];
  return Object.fromEntries(headers.map((header, index) => [compact(header), compact(cells[index] ?? "")]));
}

function first(record: Record<string, string>, ...keys: string[]): string {
  for (const key of keys) {
    if (record[key]) return record[key]!;
  }
  return "";
}

function sourceConfidence(document: ParsedDocument): number {
  switch (document.sourceType) {
    case "MODEL_CATALOG":
    case "DATA_DICTIONARY":
      return 0.98;
    case "KPI_DEFINITION":
      return 0.96;
    case "USE_CASE_SPECIFICATION":
      return 0.92;
    default:
      return 0.8;
  }
}

function addConceptFact(
  acc: ExtractionAccumulator,
  subject: Entity,
  predicate: string,
  name: string,
  evidenceId: string,
): void {
  if (!name) return;
  const concept = acc.addEntity({
    entityType: "BUSINESS_CONCEPT",
    name,
    evidenceIds: [evidenceId],
    properties: { conceptKind: predicate },
  });
  acc.addFact({
    subjectId: subject.entityId,
    predicate,
    objectId: concept.entityId,
    assertionType: "EXPLICIT",
    confidence: 0.98,
    evidenceIds: [evidenceId],
  });
}

function extractModelCatalog(document: ParsedDocument, acc: ExtractionAccumulator): void {
  let layer = "";
  let domain = "";
  let subject = "";
  for (const block of document.blocks.filter((item) => item.kind === "table_row")) {
    const sheet = block.location.sheet;
    const record = rowRecord(block);
    if (sheet === "所有领域") {
      const directLayer = first(record, "模型分层");
      const directDomain = first(record, "主题域/对象");
      const directSubject = first(record, "主题/子对象");
      const modelName = first(record, "数据模型名称");
      if (directLayer) {
        layer = directLayer;
        if (!modelName) {
          domain = "";
          subject = "";
        }
      }
      if (directDomain) {
        domain = directDomain;
        if (!modelName) subject = "";
      }
      if (directSubject) subject = directSubject;
      if (!modelName || modelName === "数据模型名称") continue;
      const evidence = acc.addEvidence(document, block, sourceConfidence(document));
      const description = first(record, "模型说明");
      const model = acc.addEntity({
        entityType: "PHYSICAL_MODEL",
        name: modelName,
        code: modelName,
        description,
        evidenceIds: [evidence.evidenceId],
        properties: {
          layer: directLayer || layer,
          domain: directDomain || domain,
          subject: directSubject || subject,
          storage: first(record, "数据存储"),
          cycle: first(record, "周期"),
          sourceVersion: first(record, "版本时间"),
          dataType: first(record, "数据类型"),
          application: first(record, "归属APP"),
          tableName: first(record, "表名"),
        },
      });
      addConceptFact(acc, model, "HAS_LAYER", directLayer || layer, evidence.evidenceId);
      addConceptFact(acc, model, "BELONGS_TO_DOMAIN", directDomain || domain, evidence.evidenceId);
      addConceptFact(acc, model, "BELONGS_TO_SUBJECT", directSubject || subject, evidence.evidenceId);
      const applicationName = first(record, "归属APP");
      if (applicationName) {
        const application = acc.addEntity({ entityType: "APPLICATION", name: applicationName, evidenceIds: [evidence.evidenceId] });
        acc.addFact({
          subjectId: model.entityId,
          predicate: "USED_BY",
          objectId: application.entityId,
          assertionType: "EXPLICIT",
          confidence: 0.98,
          evidenceIds: [evidence.evidenceId],
        });
      }
      continue;
    }
    if (!sheet || sheet === "所有领域") continue;
    const fieldCode = first(record, "数据库字段名称");
    if (!fieldCode || fieldCode === "数据库字段名称") continue;
    extractFieldRow(document, block, acc, sheet, record);
  }
}

function extractFieldRow(
  document: ParsedDocument,
  block: ParsedBlock,
  acc: ExtractionAccumulator,
  modelName: string,
  record = rowRecord(block),
): void {
  const fieldCode = first(record, "数据库字段名称");
  if (!fieldCode) return;
  const evidence = acc.addEvidence(document, block, sourceConfidence(document));
  const model = acc.addEntity({ entityType: "PHYSICAL_MODEL", name: modelName, code: modelName, evidenceIds: [evidence.evidenceId] });
  const role = first(record, "字段类型");
  const field = acc.addEntity({
    entityType: "PHYSICAL_FIELD",
    name: first(record, "字段名称") || fieldCode,
    code: `${modelName}.${fieldCode}`,
    aliases: [fieldCode],
    description: first(record, "字段说明"),
    evidenceIds: [evidence.evidenceId],
    properties: {
      physicalName: fieldCode,
      modelCode: modelName,
      dataType: first(record, "数据类型", "字段类型"),
      fieldRole: role || undefined,
      unit: first(record, "单位"),
      valueRange: first(record, "取值范围"),
      open: first(record, "是否开放"),
    },
  });
  acc.addFact({
    subjectId: model.entityId,
    predicate: "HAS_FIELD",
    objectId: field.entityId,
    assertionType: "EXPLICIT",
    confidence: 0.99,
    evidenceIds: [evidence.evidenceId],
  });
  if (role && /dimension|counter|measure/i.test(role)) {
    const roleType = /dimension/i.test(role) ? "DIMENSION" : /counter/i.test(role) ? "COUNTER" : "MEASURE";
    const semanticRole = acc.addEntity({ entityType: roleType, name: field.name, code: fieldCode, evidenceIds: [evidence.evidenceId] });
    acc.addFact({
      subjectId: field.entityId,
      predicate: "HAS_ROLE",
      objectId: semanticRole.entityId,
      assertionType: "CANDIDATE",
      confidence: 0.72,
      evidenceIds: [evidence.evidenceId],
      qualifiers: { rawRole: role },
    });
  }
}

function extractDataDictionary(document: ParsedDocument, acc: ExtractionAccumulator): void {
  for (const block of document.blocks.filter((item) => item.kind === "table_row")) {
    const record = rowRecord(block);
    const modelName = first(record, "数据模型名称");
    if (modelName) {
      const evidence = acc.addEvidence(document, block, sourceConfidence(document));
      acc.addEntity({
        entityType: "PHYSICAL_MODEL",
        name: modelName,
        code: modelName,
        description: first(record, "模型说明"),
        evidenceIds: [evidence.evidenceId],
        properties: {
          subject: first(record, "主题/子对象"),
          storage: first(record, "数据存储"),
          cycle: first(record, "周期"),
          sourceVersion: first(record, "支持版本"),
        },
      });
    }
    if (first(record, "数据库字段名称")) {
      const parent = block.sectionPath.at(-1) || "UNKNOWN_MODEL";
      extractFieldRow(document, block, acc, parent.replace(/（\d+）$/, ""), record);
    }
  }
}

function extractBracketTerms(formula: string): string[] {
  return unique([...formula.matchAll(/\[([^\]]+)\]/g)].map((match) => compact(match[1]!)).filter(Boolean));
}

function splitDimensions(value: string): string[] {
  return value.split(/[、,，/]/).map(compact).filter((item) => item && !/维度$/.test(item));
}

function extractKpiDefinitions(document: ParsedDocument, acc: ExtractionAccumulator): void {
  for (const block of document.blocks.filter((item) => item.kind === "table_row")) {
    const record = rowRecord(block);
    const metricName = first(record, "计算指标", "指标名称");
    if (!metricName) continue;
    const formulaText = first(record, "计算公式", "公式");
    const evidence = acc.addEvidence(document, block, sourceConfidence(document));
    const isCounter = /次数|时长|数量|流量/.test(metricName) && !/[率比]|MOS/i.test(metricName);
    const metric = acc.addEntity({
      entityType: isCounter ? "COUNTER" : "KPI",
      name: metricName,
      aliases: [metricName.replace(/\([^)]*\)/g, "").trim()],
      description: first(record, "打点位置"),
      evidenceIds: [evidence.evidenceId],
      properties: {
        interface: first(record, "采集接口"),
        probe: first(record, "探针"),
        dimensions: first(record, "维度"),
      },
    });
    let formula: Entity | undefined;
    if (formulaText && !(isCounter && normalize(formulaText) === normalize(`[${metricName}]`))) {
      formula = acc.addEntity({
        entityType: "FORMULA",
        name: `${metricName} formula`,
        description: formulaText,
        properties: { expression: formulaText },
        evidenceIds: [evidence.evidenceId],
      });
      acc.addFact({
        subjectId: metric.entityId,
        predicate: "CALCULATED_BY",
        objectId: formula.entityId,
        assertionType: "EXPLICIT",
        confidence: 0.97,
        evidenceIds: [evidence.evidenceId],
      });
    }
    for (const term of extractBracketTerms(formulaText)) {
      if (normalize(term) === normalize(metricName) || /统计周期/.test(term)) continue;
      const counter = acc.addEntity({ entityType: "COUNTER", name: term, evidenceIds: [evidence.evidenceId] });
      acc.addFact({
        subjectId: (formula ?? metric).entityId,
        predicate: "USES_COUNTER",
        objectId: counter.entityId,
        assertionType: "EXPLICIT",
        confidence: 0.96,
        evidenceIds: [evidence.evidenceId],
      });
    }
    for (const dimensionName of splitDimensions(first(record, "维度"))) {
      const dimension = acc.addEntity({ entityType: "DIMENSION", name: dimensionName, evidenceIds: [evidence.evidenceId] });
      acc.addFact({
        subjectId: metric.entityId,
        predicate: "HAS_DIMENSION",
        objectId: dimension.entityId,
        assertionType: "EXPLICIT",
        confidence: 0.96,
        evidenceIds: [evidence.evidenceId],
      });
    }
    const interfaceName = first(record, "采集接口");
    if (interfaceName) {
      const source = acc.addEntity({ entityType: "DATA_SOURCE", name: interfaceName, evidenceIds: [evidence.evidenceId] });
      acc.addFact({
        subjectId: metric.entityId,
        predicate: "OBSERVED_ON",
        objectId: source.entityId,
        assertionType: "EXPLICIT",
        confidence: 0.95,
        evidenceIds: [evidence.evidenceId],
      });
    }
  }
}

export function extractDocument(document: ParsedDocument, accumulator: ExtractionAccumulator): void {
  switch (document.sourceType) {
    case "MODEL_CATALOG":
      extractModelCatalog(document, accumulator);
      break;
    case "DATA_DICTIONARY":
      extractDataDictionary(document, accumulator);
      break;
    case "KPI_DEFINITION":
      extractKpiDefinitions(document, accumulator);
      break;
  }
}

function overlapScore(left: string, right: string): number {
  const terms = (value: string) => {
    const prepared = value.toLocaleLowerCase().replace(/s1mme/g, "s1-mme");
    const abbreviations = [...prepared.matchAll(/[a-z0-9]+(?:[/-][a-z0-9]+)+/g)]
      .map((match) => normalize(match[0]))
      .filter((token) => token.length >= 3);
    return unique([
      ...prepared
        .split(/[^a-z0-9\u4e00-\u9fff-]+/)
        .map(normalize)
        .filter((token) => token.length >= 3),
      ...abbreviations,
    ]);
  };
  const leftTerms = terms(left);
  const rightTerms = new Set(terms(right));
  if (!leftTerms.length) return 0;
  return leftTerms.filter((term) => rightTerms.has(term)).length / leftTerms.length;
}

export function linkSemanticCandidates(acc: ExtractionAccumulator): void {
  const entities = acc.entities();
  const models = entities.filter((entity) => entity.entityType === "PHYSICAL_MODEL");
  const requirements = entities.filter((entity) => entity.entityType === "DATA_REQUIREMENT" || entity.entityType === "DATA_SOURCE");
  for (const requirement of requirements) {
    const requirementText = [requirement.name, requirement.code, ...requirement.aliases].filter(Boolean).join(" ");
    const ranked = models
      .map((model) => ({
        model,
        score: overlapScore(requirementText, [model.name, model.code, model.description].filter(Boolean).join(" ")),
      }))
      .filter((item) => item.score > 0)
      .sort((a, b) => b.score - a.score)
      .slice(0, 8);
    for (const { model, score } of ranked) {
      acc.addFact({
        subjectId: requirement.entityId,
        predicate: "SATISFIED_BY",
        objectId: model.entityId,
        assertionType: "CANDIDATE",
        confidence: Number((0.5 + Math.min(score, 1) * 0.3).toFixed(2)),
        evidenceIds: unique([...requirement.evidenceIds, ...model.evidenceIds]),
        qualifiers: { linker: "token_overlap_v0.1" },
      });
    }
  }
}
