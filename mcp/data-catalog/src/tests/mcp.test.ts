import assert from "node:assert/strict";
import type { AddressInfo } from "node:net";
import { after, before, describe, it } from "node:test";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { InMemoryTransport } from "@modelcontextprotocol/sdk/inMemory.js";
import { createDataCatalogServer } from "../mcp/server.js";
import { createMockMetadataServer } from "../mock/server.js";
import { HttpDataCatalogProvider } from "../providers/http-provider.js";

describe("Data Catalog MCP", () => {
  const mockServer = createMockMetadataServer();
  const client = new Client({ name: "data-catalog-test", version: "0.1.0" });

  before(async () => {
    await new Promise<void>((resolve) => mockServer.listen(0, "127.0.0.1", resolve));
    const address = mockServer.address() as AddressInfo;
    const provider = new HttpDataCatalogProvider({
      baseUrl: `http://127.0.0.1:${address.port}`,
      timeoutMs: 2000,
    });
    const mcpServer = createDataCatalogServer(provider);
    const [clientTransport, serverTransport] = InMemoryTransport.createLinkedPair();
    await Promise.all([mcpServer.connect(serverTransport), client.connect(clientTransport)]);
  });

  after(async () => {
    await client.close();
    await new Promise<void>((resolve, reject) =>
      mockServer.close((error) => (error ? reject(error) : resolve())),
    );
  });

  it("registers exactly four read-only MetaOne environment tools", async () => {
    const tools = await client.listTools();
    const names = new Set(tools.tools.map((tool) => tool.name));
    const required = new Set([
      "metaone_get_capabilities",
      "metaone_search_assets",
      "metaone_get_asset",
      "metaone_expand_assets",
    ]);
    assert.equal(names.size, required.size);
    for (const name of required) assert.ok(names.has(name), `missing required tool: ${name}`);
  });

  it("exposes authoritative Compiler sources separately from Serving shortcuts", async () => {
    const result = await client.callTool({
      name: "metaone_get_capabilities",
      arguments: {},
    });
    assert.equal(result.isError, undefined);
    const structured = result.structuredContent as {
      sourceInterfaces: Array<{
        key: string;
        path: string;
        priority: string;
        phase: string;
        authority: string;
      }>;
    };
    const dimension = structured.sourceInterfaces.find((item) => item.key === "dimension-domain");
    assert.deepEqual(
      dimension && [dimension.path, dimension.priority, dimension.phase, dimension.authority],
      ["/plat/meta/v1/dimensions/", "P0", "compiler", "primary"],
    );
    const bundle = structured.sourceInterfaces.find((item) => item.key === "entity-semantic-bundle");
    assert.deepEqual(
      bundle && [bundle.path, bundle.priority, bundle.phase, bundle.authority],
      ["/entity/v1/entityColumnRelationById", "P1", "serving", "verification"],
    );
    const lineage = structured.sourceInterfaces.find((item) => item.key === "physical-lineage-v2");
    assert.equal(lineage?.path, "/meta/lineage/v2/queryByModel");
  });

  it("calls focused relation expansion over MCP", async () => {
    const result = await client.callTool({
      name: "metaone_expand_assets",
      arguments: {
        ids: ["indicator:drop-call-rate"],
        relations: ["CALCULATED_FROM"],
        limit: 10,
      },
    });
    assert.equal(result.isError, undefined);
    const structured = result.structuredContent as {
      relations: Array<{ predicate: string }>;
    };
    assert.ok(structured.relations.length > 0);
    assert.ok(structured.relations.every((item) => item.predicate === "CALCULATED_FROM"));
  });
});
