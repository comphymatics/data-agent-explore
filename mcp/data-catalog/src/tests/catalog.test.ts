import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { CatalogIndex } from "../domain/catalog.js";
import { telecomDataset } from "../mock/dataset.js";

describe("CatalogIndex", () => {
  const index = new CatalogIndex(telecomDataset);

  it("searches a telecom indicator by Chinese name and alias", () => {
    const hits = index.search({ query: "产品退订率", types: ["INDICATOR"] });
    assert.equal(hits[0]?.asset.id, "indicator:churn-rate");
    assert.ok((hits[0]?.score ?? 0) >= 0.9);

    const aliasHits = index.search({ query: "流失率", types: ["INDICATOR"] });
    assert.equal(aliasHits[0]?.asset.id, "indicator:churn-rate");
    assert.ok(aliasHits[0]?.matchedBy.includes("exact_alias"));
  });

  it("filters searches by telecom domain", () => {
    const hits = index.search({ query: "客户", domain: "Customer" });
    assert.ok(hits.length > 0);
    assert.ok(hits.every((hit) => hit.asset.domain === "Customer"));
  });

  it("expands bounded context without exceeding maxNodes", () => {
    const context = index.getContext("indicator:churn-rate", 5, 8);
    assert.ok(context);
    assert.ok(context.nodes.length <= 8);
    assert.equal(context.focus.id, "indicator:churn-rate");
    assert.equal(context.truncated, true);
  });

  it("finds an explainable path from churn indicator to a physical table", () => {
    const paths = index.findPaths("indicator:churn-rate", {
      targetTypes: ["PHYSICAL_TABLE"],
      maxDepth: 5,
      limit: 10,
    });
    assert.ok(paths.length > 0);
    assert.ok(paths.some((path) => path.nodes.at(-1)?.id === "physical:dwd-product-subscription"));
    assert.ok(paths.every((path) => path.edges.length <= 5));
  });

  it("explains edges with evidence and index version", () => {
    const explanation = index.evidenceFor("edge:churn-computed-terminated");
    assert.equal(explanation?.edge.predicate, "CALCULATED_FROM");
    assert.equal(explanation?.source?.id, "indicator:churn-rate");
    assert.equal(explanation?.target?.id, "measure:terminated-subscriptions");
    assert.equal(explanation?.evidence.length, 1);
    assert.equal(explanation?.indexVersion, telecomDataset.version);
  });
});
