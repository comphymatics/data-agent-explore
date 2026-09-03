import assert from "node:assert/strict";
import { createServer, type IncomingMessage, type ServerResponse } from "node:http";
import type { AddressInfo } from "node:net";
import { after, before, describe, it } from "node:test";
import { MetaOneApiGatewayProvider } from "../providers/metaone-api-gateway-provider.js";
import { ProviderError } from "../providers/provider.js";

function json(response: ServerResponse, status: number, body: unknown): void {
  response.writeHead(status, { "content-type": "application/json" });
  response.end(JSON.stringify(body));
}

async function body(request: IncomingMessage): Promise<Record<string, unknown>> {
  const chunks: Buffer[] = [];
  for await (const chunk of request) chunks.push(Buffer.from(chunk));
  return JSON.parse(Buffer.concat(chunks).toString("utf8") || "{}");
}

describe("MetaOneApiGatewayProvider", () => {
  let baseUrl = "";
  const requests: Array<{ path: string; authorization?: string; body?: Record<string, unknown> }> = [];
  const server = createServer(async (request, response) => {
    const url = new URL(request.url ?? "/", `http://${request.headers.host}`);
    if (url.pathname === "/entity/list") {
      requests.push({
        path: url.pathname,
        authorization: request.headers.authorization,
      });
      json(response, 200, {
        assets: [{
          id: "metaone:LOGICAL_ENTITY:1001",
          type: "LOGICAL_ENTITY",
          code: "Subscriber",
          name: "用户",
          description: "当前环境逻辑实体",
          aliases: ["订户"],
          domain: "Customer",
          attributes: { providerId: "1001" },
          evidenceRefs: ["metaone:entity:1001"],
        }, {
          id: "metaone:LOGICAL_ENTITY:1002",
          type: "LOGICAL_ENTITY",
          code: "Account",
          name: "账户",
          domain: "Billing",
          attributes: { providerId: "1002" },
        }],
        total: 2,
        complete: true,
        snapshotToken: "snapshot-7",
        capturedAt: "2026-09-03T00:00:00Z",
      });
      return;
    }
    if (url.pathname === "/entity/bundle") {
      const parsedBody = await body(request);
      requests.push({ path: url.pathname, body: parsedBody });
      json(response, 200, {
        assets: [
          {
            id: "metaone:LOGICAL_ENTITY:1001",
            type: "LOGICAL_ENTITY",
            name: "用户",
            attributes: {},
          },
          {
            id: "metaone:PHYSICAL_COLUMN:2001",
            type: "PHYSICAL_COLUMN",
            name: "用户标识字段",
            attributes: {},
          },
        ],
        relations: [{
          id: "metaone:relation:1",
          sourceId: "metaone:LOGICAL_ENTITY:1001",
          predicate: "MAPS_TO",
          targetId: "metaone:PHYSICAL_COLUMN:2001",
          evidenceRefs: ["metaone:bundle:1"],
        }],
        complete: true,
      });
      return;
    }
    if (url.pathname === "/raw") {
      json(response, 200, { data: { entityId: "1001", entityName: "用户" } });
      return;
    }
    if (url.pathname === "/unauthorized") {
      json(response, 403, { error: "forbidden" });
      return;
    }
    json(response, 404, { error: "not found" });
  });

  before(async () => {
    await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
    baseUrl = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
  });

  after(async () => {
    await new Promise<void>((resolve, reject) =>
      server.close((error) => (error ? reject(error) : resolve())),
    );
  });

  it("discovers configured source capabilities and searches through the gateway", async () => {
    const provider = new MetaOneApiGatewayProvider({
      baseUrl,
      environmentId: "tenant-a",
      headers: { authorization: "Bearer fixture-token" },
      routes: [
        { endpointKey: "logical-model-list", method: "GET", path: "/entity/list" },
        { endpointKey: "entity-semantic-bundle", method: "POST", path: "/entity/bundle" },
      ],
    });
    const capabilities = await provider.getCapabilities();
    assert.equal(capabilities.provider, "metaone-api-gateway");
    assert.match(String(capabilities.capabilityRevision), /^gateway-routes-/);

    const result = await provider.searchAssets({
      query: "用户",
      types: ["LOGICAL_ENTITY"],
      limit: 5,
    });
    const records = result.records as Array<{ asset: { id: string } }>;
    assert.equal(records[0]?.asset.id, "metaone:LOGICAL_ENTITY:1001");
    assert.equal(result.complete, true);
    assert.equal(result.total, 1);
    assert.equal(result.snapshotToken, "snapshot-7");
    assert.equal(requests.at(-1)?.authorization, "Bearer fixture-token");

    const expanded = await provider.expandAssets({
      ids: ["metaone:LOGICAL_ENTITY:1001"],
      relations: ["MAPS_TO"],
      limit: 10,
    });
    assert.equal((expanded.relations as Array<{ predicate: string }>)[0]?.predicate, "MAPS_TO");
    assert.deepEqual(requests.at(-1)?.body?.ids, ["1001"]);
  });

  it("fails closed for an unnormalized raw MetaOne payload", async () => {
    const provider = new MetaOneApiGatewayProvider({
      baseUrl,
      routes: [{ endpointKey: "logical-model-list", method: "GET", path: "/raw" }],
    });
    await assert.rejects(
      provider.searchAssets({ query: "用户", types: ["LOGICAL_ENTITY"] }),
      (error: unknown) => error instanceof ProviderError && error.category === "INVALID_RESPONSE",
    );
  });

  it("classifies gateway authorization failures", async () => {
    const provider = new MetaOneApiGatewayProvider({
      baseUrl,
      routes: [{ endpointKey: "logical-model-list", method: "GET", path: "/unauthorized" }],
    });
    await assert.rejects(
      provider.searchAssets({ query: "用户", types: ["LOGICAL_ENTITY"] }),
      (error: unknown) => error instanceof ProviderError && error.category === "UNAUTHORIZED",
    );
  });

  it("does not turn a missing route into confirmed absence", async () => {
    const provider = new MetaOneApiGatewayProvider({
      baseUrl,
      routes: [{ endpointKey: "dimension-domain", method: "GET", path: "/dimensions" }],
    });
    const result = await provider.searchAssets({
      query: "用户",
      types: ["LOGICAL_ENTITY"],
    });
    assert.equal(result.complete, false);
    assert.equal(result.truncated, true);
    assert.equal((result.warnings as Array<{ code: string }>)[0]?.code, "gateway_search_route_unavailable");
  });
});
