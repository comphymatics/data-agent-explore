import { readFileSync } from "node:fs";
import { HttpDataCatalogProvider } from "./http-provider.js";
import {
  MetaOneApiGatewayProvider,
  type GatewayRouteBinding,
} from "./metaone-api-gateway-provider.js";
import type { DataCatalogProvider } from "./provider.js";

interface GatewayConfigFile {
  baseUrl?: string;
  environmentId?: string;
  timeoutMs?: number;
  maxFanout?: number;
  headers?: Record<string, string>;
  livePayloadMappingVerified?: boolean;
  routes: GatewayRouteBinding[];
}

export function createProviderFromEnvironment(): DataCatalogProvider {
  const configPath = process.env.METAONE_API_GATEWAY_CONFIG;
  const gatewayBaseUrl = process.env.METAONE_API_GATEWAY_BASE_URL;
  if (!configPath && !gatewayBaseUrl) {
    return new HttpDataCatalogProvider({
      baseUrl: process.env.DATA_CATALOG_BASE_URL ?? "http://127.0.0.1:4100",
      timeoutMs: Number(process.env.DATA_CATALOG_TIMEOUT_MS ?? 5000),
    });
  }
  if (!configPath) {
    throw new Error(
      "METAONE_API_GATEWAY_CONFIG is required when METAONE_API_GATEWAY_BASE_URL is set",
    );
  }
  const config = parseGatewayConfig(configPath);
  const baseUrl = gatewayBaseUrl ?? config.baseUrl;
  if (!baseUrl) {
    throw new Error("MetaOne API gateway baseUrl is missing from environment and config");
  }
  const headers = { ...(config.headers ?? {}) };
  const token = process.env.METAONE_API_GATEWAY_TOKEN;
  if (token) {
    const header = process.env.METAONE_API_GATEWAY_AUTH_HEADER ?? "authorization";
    const scheme = process.env.METAONE_API_GATEWAY_AUTH_SCHEME ?? "Bearer";
    headers[header] = scheme ? `${scheme} ${token}` : token;
  }
  return new MetaOneApiGatewayProvider({
    baseUrl,
    routes: config.routes,
    environmentId: process.env.METAONE_ENVIRONMENT_ID ?? config.environmentId,
    timeoutMs: Number(process.env.METAONE_API_GATEWAY_TIMEOUT_MS ?? config.timeoutMs ?? 8000),
    maxFanout: Number(process.env.METAONE_API_GATEWAY_MAX_FANOUT ?? config.maxFanout ?? 8),
    livePayloadMappingVerified: config.livePayloadMappingVerified === true,
    headers,
  });
}

function parseGatewayConfig(path: string): GatewayConfigFile {
  let value: unknown;
  try {
    value = JSON.parse(readFileSync(path, "utf8"));
  } catch (error) {
    throw new Error(
      `cannot read MetaOne API gateway config ${path}: ${error instanceof Error ? error.message : String(error)}`,
    );
  }
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("MetaOne API gateway config must be a JSON object");
  }
  const config = value as Partial<GatewayConfigFile>;
  if (!Array.isArray(config.routes) || config.routes.length === 0) {
    throw new Error("MetaOne API gateway config requires at least one route");
  }
  for (const route of config.routes) {
    if (!route || typeof route !== "object" || !route.endpointKey) {
      throw new Error("every MetaOne API gateway route requires endpointKey");
    }
    if (route.method !== "GET" && route.method !== "POST") {
      throw new Error(`route ${route.endpointKey} method must be GET or POST`);
    }
    if (route.includeArguments && !Array.isArray(route.includeArguments)) {
      throw new Error(`route ${route.endpointKey} includeArguments must be an array`);
    }
  }
  return config as GatewayConfigFile;
}
