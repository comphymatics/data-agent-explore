import { createServer, type IncomingMessage, type ServerResponse } from "node:http";
import { fileURLToPath } from "node:url";
import { CatalogIndex } from "../domain/catalog.js";
import type { AssetType } from "../domain/types.js";
import { METAONE_ENDPOINTS, METAONE_RELATIONS } from "../metaone/endpoints.js";
import { telecomDataset } from "./dataset.js";

const index = new CatalogIndex(telecomDataset);

function json(response: ServerResponse, status: number, body: unknown): void {
  response.writeHead(status, {
    "content-type": "application/json; charset=utf-8",
    "access-control-allow-origin": "*",
  });
  response.end(JSON.stringify(body, null, 2));
}

function getUrl(request: IncomingMessage): URL {
  return new URL(request.url ?? "/", `http://${request.headers.host ?? "127.0.0.1"}`);
}

export function createMockMetadataServer() {
  return createServer((request, response) => {
    if (request.method !== "GET") {
      json(response, 405, { error: "METHOD_NOT_ALLOWED" });
      return;
    }
    const url = getUrl(request);
    if (url.pathname === "/health") {
      json(response, 200, { status: "ok", service: "telecom-metadata-mock", version: telecomDataset.version });
      return;
    }
    if (url.pathname === "/v1/capabilities") {
      json(response, 200, {
        provider: "metaone-fixture",
        environmentId: "fixture-tenant",
        capabilityRevision: "metaone-interface-inventory-v1",
        accessMode: "tenant_service_account",
        tenantIsolation: true,
        authorizationFiltering: false,
        datasetVersion: telecomDataset.version,
        assetTypes: [...new Set(telecomDataset.assets.map((item) => item.type))],
        relations: METAONE_RELATIONS,
        sourceInterfaces: METAONE_ENDPOINTS,
        completeness: {
          interfaceInventory: true,
          livePayloadMappingVerified: false,
        },
      });
      return;
    }
    if (url.pathname === "/v1/assets/search") {
      const types = url.searchParams.getAll("type") as AssetType[];
      const hits = index.search({
        query: url.searchParams.get("q") ?? "",
        types: types.length ? types : undefined,
        domain: url.searchParams.get("domain") ?? undefined,
        limit: Number(url.searchParams.get("limit") ?? 20),
      });
      json(response, 200, {
        records: hits,
        total: hits.length,
        complete: true,
        coverage: {
          metrics: hits.some((hit) => ["INDICATOR", "MEASURE"].includes(hit.asset.type)),
          dimensions: hits.some((hit) => hit.asset.type === "DIMENSION"),
          models: hits.some((hit) => ["LOGICAL_ENTITY", "PHYSICAL_TABLE"].includes(hit.asset.type)),
          fields: hits.some((hit) => ["LOGICAL_ATTRIBUTE", "PHYSICAL_COLUMN"].includes(hit.asset.type)),
          lineage: false,
        },
        version: telecomDataset.version,
      });
      return;
    }
    if (url.pathname === "/v1/assets/expand") {
      const ids = url.searchParams.getAll("id");
      const relations = url.searchParams.getAll("relation");
      const expanded = index.expand(ids, {
        relations: relations.length ? relations : undefined,
        limit: Number(url.searchParams.get("limit") ?? 50),
      });
      json(response, 200, {
        ...expanded,
        records: expanded.assets,
        version: telecomDataset.version,
      });
      return;
    }
    const assetMatch = url.pathname.match(/^\/v1\/assets\/(.+)$/);
    if (assetMatch) {
      const id = decodeURIComponent(assetMatch[1]!);
      const context = index.getContext(
        id,
        Number(url.searchParams.get("depth") ?? 2),
        Number(url.searchParams.get("maxNodes") ?? 50),
      );
      if (!context) {
        json(response, 404, { error: "ASSET_NOT_FOUND", id });
        return;
      }
      json(response, 200, { ...context, version: telecomDataset.version });
      return;
    }
    if (url.pathname === "/v1/dataset") {
      json(response, 200, telecomDataset);
      return;
    }
    json(response, 404, { error: "ROUTE_NOT_FOUND", path: url.pathname });
  });
}

const isMain = process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1];
if (isMain) {
  const port = Number(process.env.MOCK_METADATA_PORT ?? 4100);
  const host = process.env.MOCK_METADATA_HOST ?? "127.0.0.1";
  createMockMetadataServer().listen(port, host, () => {
    console.error(`telecom metadata mock listening at http://${host}:${port}`);
  });
}
