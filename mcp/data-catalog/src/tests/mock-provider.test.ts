import assert from "node:assert/strict";
import type { AddressInfo } from "node:net";
import { after, before, describe, it } from "node:test";
import { createMockMetadataServer } from "../mock/server.js";
import { HttpDataCatalogProvider } from "../providers/http-provider.js";

describe("telecom metadata mock and HTTP provider", () => {
  const server = createMockMetadataServer();
  let provider: HttpDataCatalogProvider;

  before(async () => {
    await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
    const address = server.address() as AddressInfo;
    provider = new HttpDataCatalogProvider({
      baseUrl: `http://127.0.0.1:${address.port}`,
      timeoutMs: 2000,
    });
  });

  after(async () => {
    await new Promise<void>((resolve, reject) =>
      server.close((error) => (error ? reject(error) : resolve())),
    );
  });

  it("reports supported telecom metadata capabilities", async () => {
    const capabilities = await provider.getCapabilities();
    assert.equal(capabilities.provider, "metaone-fixture");
    assert.equal(capabilities.tenantIsolation, true);
    assert.ok(Array.isArray(capabilities.assetTypes));
    assert.ok(Array.isArray(capabilities.sourceInterfaces));
    assert.equal(
      (capabilities.completeness as { livePayloadMappingVerified: boolean }).livePayloadMappingVerified,
      false,
    );
  });

  it("searches through the network provider boundary", async () => {
    const result = await provider.searchAssets({
      query: "掉话率",
      types: ["INDICATOR"],
      limit: 5,
    });
    const records = result.records as Array<{ asset: { id: string } }>;
    assert.equal(records[0]?.asset.id, "indicator:drop-call-rate");
  });

  it("returns physical-logical-SID context from the mock service", async () => {
    const result = await provider.getAssetContext("physical:dwd-product-subscription", 2, 50);
    const nodes = result.nodes as Array<{ type: string }>;
    assert.ok(nodes.some((node) => node.type === "LOGICAL_ENTITY"));
    assert.ok(nodes.some((node) => node.type === "PHYSICAL_COLUMN"));
  });

  it("expands only requested deterministic relations", async () => {
    const result = await provider.expandAssets({
      ids: ["indicator:drop-call-rate"],
      relations: ["COMPUTED_FROM"],
      limit: 10,
    });
    const relations = result.relations as Array<{ predicate: string }>;
    assert.ok(relations.length > 0);
    assert.ok(relations.every((relation) => relation.predicate === "COMPUTED_FROM"));
  });
});
