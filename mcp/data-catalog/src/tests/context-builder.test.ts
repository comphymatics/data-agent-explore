import assert from "node:assert/strict";
import { existsSync } from "node:fs";
import { resolve } from "node:path";
import { before, describe, it } from "node:test";
import { ContextBuilder } from "../context-builder/builder.js";
import { OfflineContextEngine } from "../context-builder/engine.js";
import { ContextIndexEngine } from "../context-builder/index-engine.js";
import { parserFor } from "../context-builder/parsers/parser.js";
import type { ContextGraph } from "../context-builder/schema.js";
import { InMemoryContextStore } from "../context-builder/store.js";

const source = (name: string) => resolve("../../docs/source", name);
const inputs = [
  source("DataCube数据模型资产目录5.2 - mini.xlsx"),
  source("Smart DataCube 7.3.0 数据字典（客户版） - mini(1).docx"),
  source("HUAWEI SmartCare® 7.3.0 建模文档（for GTS）-mini.docx"),
];
const describeWithSourceFixtures = inputs.every(existsSync) ? describe : describe.skip;

describeWithSourceFixtures("Explore Context Builder v0.1 (external source fixtures)", () => {
  let graph: ContextGraph;
  let store: InMemoryContextStore;
  let index: ContextIndexEngine;

  before(async () => {
    graph = await new ContextBuilder({
      sourceVersion: "mini-test",
      now: () => new Date("2026-08-21T00:00:00.000Z"),
    }).build(inputs);
    store = new InMemoryContextStore(graph);
    index = new ContextIndexEngine(store);
  });

  it("parses XLSX rows and DOCX tables with precise source locations", async () => {
    assert.throws(() => parserFor(source("09-lte-metro-usecase.md")), /unsupported document format/);
    const workbook = await parserFor(inputs[0]!).parse(inputs[0]!);
    const modelRow = workbook.blocks.find(
      (block) => block.location.sheet === "所有领域" && block.location.row === 42,
    );
    assert.ok(modelRow?.text.includes("DETAIL_CDR_S1MME"));

    const dictionary = await parserFor(inputs[1]!).parse(inputs[1]!);
    const catalogRow = dictionary.blocks.find(
      (block) => block.kind === "table_row" && block.cells?.includes("CDR_AIU_MTC"),
    );
    assert.equal(catalogRow?.cells?.[0], "CS XDR（19）");
    assert.equal(catalogRow?.cells?.[1], "CDR_AIU_MTC");
    assert.equal(catalogRow?.location.table, 1);
  });

  it("extracts canonical entities, facts and evidence without dangling references", () => {
    assert.equal(graph.documents.length, 3);
    assert.ok(graph.documents.every((document) => /\.(xlsx|docx)$/i.test(document.sourceUri)));
    assert.ok(graph.entities.length > 1_000);
    assert.ok(graph.facts.length > 2_000);
    assert.ok(graph.evidence.length > 1_000);
    assert.match(graph.indexVersion, /^context-v0\.1-[a-f0-9]{12}$/);

    const model = store.getEntity("pm:smartcare:detail_cdr_s1mme");
    assert.equal(model?.entityType, "PHYSICAL_MODEL");
    assert.equal(model?.description, "信令面S1-MME接口常用流程单据");
    const evidence = model?.evidenceIds.map((id) => store.getEvidence(id));
    assert.ok(evidence?.some((item) => item?.location.sheet === "所有领域" && item.location.row === 42));

    const field = store.getEntity("pf:smartcare:cdr_aiu_moc.poolid");
    assert.equal(field?.properties.modelCode, "CDR_AIU_MOC");
    const hasField = store
      .factsForEntity(field!.entityId)
      .find((fact) => fact.predicate === "HAS_FIELD" && fact.objectId === field!.entityId);
    assert.equal(hasField?.assertionType, "EXPLICIT");
    assert.ok(hasField?.evidenceIds.length);
  });

  it("keeps field-role and cross-document interface links as candidates", () => {
    const dictionaryField = index.search({ query: "NR同频周期MR.DATATYPE", entityTypes: ["PHYSICAL_FIELD"] })[0]?.entity;
    assert.ok(dictionaryField);
    const roleFact = store.factsForEntity(dictionaryField.entityId).find((fact) => fact.predicate === "HAS_ROLE");
    assert.equal(roleFact?.assertionType, "CANDIDATE");
    assert.equal(roleFact?.status, "CANDIDATE");

    const interfaceSource = index.search({ query: "A/Iu", entityTypes: ["DATA_SOURCE"] })[0]?.entity;
    assert.ok(interfaceSource);
    const linkedModel = store
      .factsForEntity(interfaceSource.entityId)
      .find((fact) => fact.predicate === "SATISFIED_BY" && fact.objectId === "pm:smartcare:cdr_aiu_moc");
    assert.equal(linkedModel?.assertionType, "CANDIDATE");
    assert.equal(linkedModel?.qualifiers.linker, "token_overlap_v0.1");
  });

  it("supports exact-first search, evidence-backed definitions and bounded tracing", () => {
    const exact = index.search({ query: "DETAIL_CDR_S1MME", entityTypes: ["PHYSICAL_MODEL"] })[0];
    assert.equal(exact?.score, 1);
    assert.ok(exact?.matchedBy.includes("exact_code"));
    const hit = index.search({ query: "DETAIL_CDR_S1MME是什么", entityTypes: ["PHYSICAL_MODEL"] })[0];
    assert.equal(hit?.entity.entityId, "pm:smartcare:detail_cdr_s1mme");
    assert.ok(hit?.matchedBy.includes("partial_name_or_code"));

    const definition = index.definition(hit!.entity.entityId);
    assert.equal(definition?.indexVersion, graph.indexVersion);
    assert.ok(definition?.facts.some((fact) => fact.predicate === "BELONGS_TO_DOMAIN"));
    assert.ok(definition?.evidence.length);

    const fieldPaths = index.trace("pm:smartcare:cdr_aiu_moc", {
      targetId: "pf:smartcare:cdr_aiu_moc.poolid",
      maxDepth: 1,
      limit: 5,
      includeCandidates: false,
    });
    assert.ok(fieldPaths.some((path) => path.entities.at(-1)?.entityId === "pf:smartcare:cdr_aiu_moc.poolid"));
    assert.ok(fieldPaths.every((path) => path.facts.length === 1));
    assert.ok(fieldPaths.every((path) => path.facts[0]?.status === "VERIFIED"));
  });

  it("exposes data_find, data_definition and data_trace semantics without an Agent", () => {
    const engine = new OfflineContextEngine(graph);
    const found = engine.dataFind({ query: "DETAIL_CDR_S1MME", entityTypes: ["PHYSICAL_MODEL"] });
    assert.equal(found.records[0]?.entity.entityId, "pm:smartcare:detail_cdr_s1mme");
    assert.equal(found.indexVersion, graph.indexVersion);
    assert.ok(engine.dataDefinition("pm:smartcare:detail_cdr_s1mme").definition);
    assert.deepEqual(engine.dataDefinition("missing").warnings, ["entity not found: missing"]);
    assert.deepEqual(engine.dataTrace("missing", { targetTypes: ["KPI"] }).paths, []);
  });

  it("extracts KPI formulas and counters as an explainable semantic path", () => {
    const metric = index.search({ query: "无线掉话率", entityTypes: ["KPI"] })[0]?.entity;
    assert.ok(metric);
    const paths = index.trace(metric.entityId, { targetTypes: ["COUNTER"], maxDepth: 2, limit: 20 });
    assert.ok(paths.some((path) => path.entities.at(-1)?.name === "TCH掉话次数"));
    assert.ok(paths.some((path) => path.facts.map((fact) => fact.predicate).join("/") === "CALCULATED_BY/USES_COUNTER"));
    assert.ok(paths.every((path) => path.facts.every((fact) => fact.evidenceIds.length > 0)));
  });
});
