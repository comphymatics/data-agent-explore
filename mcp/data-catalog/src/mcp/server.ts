import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import type { AssetType } from "../domain/types.js";
import { METAONE_ASSET_TYPES, METAONE_RELATIONS } from "../metaone/endpoints.js";
import { HttpDataCatalogProvider } from "../providers/http-provider.js";
import type { DataCatalogProvider } from "../providers/provider.js";

const assetTypes = METAONE_ASSET_TYPES as [AssetType, ...AssetType[]];
const relations = METAONE_RELATIONS as [string, ...string[]];

const asResult = (value: unknown) => ({
  content: [{ type: "text" as const, text: JSON.stringify(value, null, 2) }],
  structuredContent: value as Record<string, unknown>,
});

/**
 * Read-only environment-metadata MCP. Explore never consumes these raw tool names;
 * MetaOneMcpAdapter negotiates and normalizes this surface first.
 */
export function createDataCatalogServer(provider?: DataCatalogProvider): McpServer {
  const catalogProvider =
    provider ??
    new HttpDataCatalogProvider({
      baseUrl: process.env.DATA_CATALOG_BASE_URL ?? "http://127.0.0.1:4100",
      timeoutMs: Number(process.env.DATA_CATALOG_TIMEOUT_MS ?? 5000),
    });
  const server = new McpServer({
    name: "metaone-environment-metadata",
    version: "0.2.0",
  });

  server.registerTool(
    "metaone_get_capabilities",
    {
      title: "Get MetaOne metadata capabilities",
      description:
        "Return versioned read-only asset, relation and source-interface capabilities for the current environment.",
      inputSchema: {},
    },
    async () => asResult(await catalogProvider.getCapabilities()),
  );

  server.registerTool(
    "metaone_search_assets",
    {
      title: "Search current-environment metadata assets",
      description:
        "Search MetaOne-backed logical models, physical models, fields, dimensions, measures, indicators and aggregate models.",
      inputSchema: {
        query: z.string().min(1).describe("Business or technical search phrase"),
        types: z.array(z.enum(assetTypes)).optional(),
        domain: z.string().optional(),
        limit: z.number().int().min(1).max(100).default(20),
        cursor: z.string().optional(),
      },
    },
    async ({ query, types, domain, limit, cursor }) =>
      asResult(
        await catalogProvider.searchAssets({
          query,
          types: types as AssetType[] | undefined,
          domain,
          limit,
          cursor,
        }),
      ),
  );

  server.registerTool(
    "metaone_get_asset",
    {
      title: "Read one current-environment metadata asset",
      description:
        "Read one asset with bounded deterministic neighbors; use focused sections instead of graph-node traversal.",
      inputSchema: {
        id: z.string().min(1),
        depth: z.number().int().min(0).max(3).default(1),
        maxNodes: z.number().int().min(1).max(200).default(50),
      },
    },
    async ({ id, depth, maxNodes }) =>
      asResult(await catalogProvider.getAssetContext(id, depth, maxNodes)),
  );

  server.registerTool(
    "metaone_expand_assets",
    {
      title: "Expand deterministic MetaOne relationships",
      description:
        "Focused expansion for fields, logical-physical mappings, dimensions, measures, indicators, roll-ups, aggregate sources or lineage.",
      inputSchema: {
        ids: z.array(z.string().min(1)).min(1).max(20),
        relations: z.array(z.enum(relations)).optional(),
        limit: z.number().int().min(1).max(200).default(50),
      },
    },
    async ({ ids, relations: requestedRelations, limit }) =>
      asResult(
        await catalogProvider.expandAssets({
          ids,
          relations: requestedRelations,
          limit,
        }),
      ),
  );

  return server;
}
