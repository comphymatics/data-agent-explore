import type { Asset, ContextEdge, ExpandInput, SearchInput } from "../domain/types.js";
import {
  METAONE_ENDPOINTS,
  type MetaOneEndpointCapability,
} from "../metaone/endpoints.js";
import { ProviderError, type DataCatalogProvider } from "./provider.js";

export type GatewayMethod = "GET" | "POST";
export type GatewayArgumentLocation = "query" | "body";

export interface GatewayRouteBinding {
  endpointKey: string;
  method: GatewayMethod;
  path?: string;
  argumentLocation?: GatewayArgumentLocation;
  includeArguments?: string[];
  argumentAliases?: Record<string, string>;
  staticArguments?: Record<string, unknown>;
}

export interface MetaOneApiGatewayOptions {
  baseUrl: string;
  routes: GatewayRouteBinding[];
  environmentId?: string;
  timeoutMs?: number;
  headers?: Record<string, string>;
  maxFanout?: number;
  livePayloadMappingVerified?: boolean;
}

interface BoundRoute {
  binding: GatewayRouteBinding;
  capability: MetaOneEndpointCapability;
}

interface NormalizedEnvelope {
  assets: Asset[];
  relations: ContextEdge[];
  focus?: Asset;
  total?: number;
  complete?: boolean;
  truncated?: boolean;
  nextCursor?: string;
  snapshotToken?: string;
  capturedAt?: string;
  warnings: Array<Record<string, unknown>>;
}

const ENVELOPE_KEYS = new Set([
  "assets",
  "records",
  "relations",
  "edges",
  "focus",
  "asset",
  "total",
  "totalCount",
  "complete",
  "truncated",
  "hasMore",
  "nextCursor",
  "snapshotToken",
  "capturedAt",
  "warnings",
]);

/**
 * Production transport over API-gateway-published MetaOne routes.
 *
 * Each published route must return a normalized envelope. Raw MetaOne payload
 * normalizers are deliberately not guessed here; add them after capturing real
 * request/response fixtures.
 */
export class MetaOneApiGatewayProvider implements DataCatalogProvider {
  private readonly baseUrl: string;
  private readonly timeoutMs: number;
  private readonly headers: Record<string, string>;
  private readonly maxFanout: number;
  private readonly routes: BoundRoute[];
  private readonly assetTypes = new Map<string, string>();
  private readonly providerIds = new Map<string, string>();

  constructor(private readonly options: MetaOneApiGatewayOptions) {
    this.baseUrl = options.baseUrl.replace(/\/+$/, "");
    this.timeoutMs = options.timeoutMs ?? 8000;
    this.headers = { accept: "application/json", ...(options.headers ?? {}) };
    this.maxFanout = Math.max(1, options.maxFanout ?? 8);
    const capabilities = new Map(METAONE_ENDPOINTS.map((endpoint) => [endpoint.key, endpoint]));
    const seen = new Set<string>();
    this.routes = options.routes.map((binding) => {
      if (seen.has(binding.endpointKey)) {
        throw new Error(`duplicate MetaOne gateway route: ${binding.endpointKey}`);
      }
      seen.add(binding.endpointKey);
      const capability = capabilities.get(binding.endpointKey);
      if (!capability) {
        throw new Error(`unknown MetaOne endpoint key: ${binding.endpointKey}`);
      }
      return { binding, capability };
    });
  }

  async getCapabilities(): Promise<Record<string, unknown>> {
    const sourceInterfaces = this.routes.map(({ binding, capability }) => ({
      ...capability,
      gatewayPath: binding.path ?? capability.path,
      method: binding.method,
    }));
    return {
      provider: "metaone-api-gateway",
      environmentId: this.options.environmentId,
      capabilityRevision: capabilityRevision(sourceInterfaces),
      operations: ["capabilities", "search", "read", "expand"],
      assetTypes: [...new Set(sourceInterfaces.flatMap((item) => item.assetTypes))].sort(),
      relations: [...new Set(sourceInterfaces.flatMap((item) => item.relations))].sort(),
      sourceInterfaces,
      compilerSourceInterfaces: sourceInterfaces.filter(
        (item) => item.phase === "compiler" && item.authority === "primary",
      ),
      completeness: {
        interfaceInventory: true,
        livePayloadMappingVerified: this.options.livePayloadMappingVerified === true,
      },
      capturedAt: new Date().toISOString(),
    };
  }

  async searchAssets(input: SearchInput): Promise<Record<string, unknown>> {
    const requestedTypes = new Set(input.types ?? []);
    const candidates = this.routes.filter(({ capability }) => {
      if (capability.role !== "search") return false;
      return (
        requestedTypes.size === 0 ||
        capability.assetTypes.some((type) => requestedTypes.has(type))
      );
    });
    const selected = candidates.slice(0, this.maxFanout);
    if (selected.length === 0) {
      return unavailablePage(
        "gateway_search_route_unavailable",
        "No configured MetaOne gateway route can search the requested asset types.",
      );
    }
    const envelopes = await Promise.all(
      selected.map((route) =>
        this.callRoute(route, {
          query: input.query,
          types: input.types,
          domain: input.domain,
          limit: input.limit,
          cursor: input.cursor,
        }),
      ),
    );
    const merged = this.merge(envelopes, selected.length < candidates.length);
    const query = normalizeText(input.query);
    const domain = input.domain ? normalizeText(input.domain) : "";
    const matchingRecords = merged.assets
      .filter((asset) => requestedTypes.size === 0 || requestedTypes.has(asset.type))
      .filter((asset) => !domain || normalizeText(asset.domain) === domain)
      .map((asset) => ({
        asset,
        score: searchScore(asset, query),
        matchedBy: searchReasons(asset, query),
      }))
      .filter((record) => record.score > 0 || query.length === 0)
      .sort((left, right) => right.score - left.score || left.asset.id.localeCompare(right.asset.id));
    const limit = input.limit ?? 20;
    const records = matchingRecords.slice(0, limit);
    const localLimitTruncated = matchingRecords.length > limit;
    return {
      records,
      total: matchingRecords.length,
      complete: merged.complete && !localLimitTruncated,
      truncated: merged.truncated || localLimitTruncated,
      nextCursor: merged.nextCursor,
      snapshotToken: merged.snapshotToken,
      capturedAt: merged.capturedAt,
      coverage: coverageFor(records.map((record) => record.asset), merged.relations),
      warnings: merged.warnings,
    };
  }

  async getAssetContext(id: string, depth = 1, maxNodes = 50): Promise<Record<string, unknown>> {
    const providerType = this.assetTypes.get(id) ?? parseProviderType(id);
    if (!providerType) {
      throw new ProviderError(
        "INVALID_REQUEST",
        `cannot infer the MetaOne asset type from id: ${id}; use a typed stable id`,
      );
    }
    const candidates = this.routes.filter(({ capability }) =>
      capability.assetTypes.includes(providerType as Asset["type"]) &&
      (capability.role === "read" || capability.role === "expand"),
    );
    const servingFirst = candidates.sort(
      (left, right) => Number(right.capability.phase === "serving") - Number(left.capability.phase === "serving"),
    );
    const selected = servingFirst.slice(0, this.maxFanout);
    if (selected.length === 0) {
      throw new ProviderError(
        "UNSUPPORTED",
        `no configured MetaOne gateway route can read asset type ${providerType}`,
      );
    }
    const providerId = this.providerIdFor(id);
    const envelopes = await Promise.all(
      selected.map((route) => this.callRoute(route, { id: providerId, depth, maxNodes })),
    );
    const merged = this.merge(envelopes, selected.length < candidates.length);
    const focus = merged.focus ?? merged.assets.find((asset) => asset.id === id);
    if (!focus) {
      throw new ProviderError("NOT_FOUND", `MetaOne asset not found: ${id}`, 404);
    }
    return {
      focus,
      nodes: merged.assets.slice(0, maxNodes),
      edges: merged.relations,
      truncated: merged.truncated || merged.assets.length > maxNodes,
      snapshotToken: merged.snapshotToken,
      capturedAt: merged.capturedAt,
      warnings: merged.warnings,
    };
  }

  async expandAssets(input: ExpandInput): Promise<Record<string, unknown>> {
    const requestedRelations = new Set(input.relations ?? []);
    const providerTypes = new Set(
      input.ids.map((id) => this.assetTypes.get(id) ?? parseProviderType(id)).filter(Boolean),
    );
    const candidates = this.routes.filter(({ capability }) => {
      if (capability.role !== "expand") return false;
      const typeMatch =
        providerTypes.size === 0 || capability.assetTypes.some((type) => providerTypes.has(type));
      const relationMatch =
        requestedRelations.size === 0 ||
        capability.relations.some((relation) => requestedRelations.has(relation));
      return typeMatch && relationMatch;
    });
    const selected = candidates.slice(0, this.maxFanout);
    if (selected.length === 0) {
      return unavailablePage(
        "gateway_expand_route_unavailable",
        "No configured MetaOne gateway route can expand the requested asset types and relations.",
      );
    }
    const providerIds = input.ids.map((id) => this.providerIdFor(id));
    const envelopes = await Promise.all(
      selected.map((route) =>
        this.callRoute(route, {
          ids: providerIds,
          id: providerIds[0],
          relations: input.relations,
          limit: input.limit,
        }),
      ),
    );
    const merged = this.merge(envelopes, selected.length < candidates.length);
    const allowedRelations = requestedRelations.size
      ? merged.relations.filter((relation) => requestedRelations.has(relation.predicate))
      : merged.relations;
    return {
      records: merged.assets.slice(0, input.limit ?? 50),
      assets: merged.assets.slice(0, input.limit ?? 50),
      relations: allowedRelations,
      complete: merged.complete,
      truncated: merged.truncated || merged.assets.length > (input.limit ?? 50),
      snapshotToken: merged.snapshotToken,
      capturedAt: merged.capturedAt,
      coverage: coverageFor(merged.assets, allowedRelations),
      warnings: merged.warnings,
    };
  }

  private async callRoute(
    route: BoundRoute,
    canonicalArguments: Record<string, unknown>,
  ): Promise<NormalizedEnvelope> {
    const { binding, capability } = route;
    const argumentsForRoute = mapArguments(binding, canonicalArguments);
    const resolved = resolvePath(binding.path ?? capability.path, argumentsForRoute);
    const path = resolved.path;
    const argumentLocation = binding.argumentLocation ?? (binding.method === "GET" ? "query" : "body");
    let url = `${this.baseUrl}${path}`;
    const request: RequestInit = {
      method: binding.method,
      headers: this.headers,
      signal: AbortSignal.timeout(this.timeoutMs),
    };
    if (argumentLocation === "query") {
      const params = toSearchParams(resolved.arguments);
      if ([...params].length) url += `${url.includes("?") ? "&" : "?"}${params}`;
    } else {
      request.headers = { "content-type": "application/json", ...this.headers };
      request.body = JSON.stringify(resolved.arguments);
    }
    try {
      const response = await fetch(url, request);
      const payload = await response.json().catch(() => undefined);
      if (!response.ok) {
        const category =
          response.status === 401 || response.status === 403
            ? "UNAUTHORIZED"
            : response.status === 404
              ? "NOT_FOUND"
              : "PROVIDER_ERROR";
        throw new ProviderError(
          category,
          `MetaOne gateway route ${capability.key} returned HTTP ${response.status}`,
          response.status,
        );
      }
      return normalizeEnvelope(payload, capability, this.options.environmentId);
    } catch (error) {
      if (error instanceof ProviderError) throw error;
      if (error instanceof DOMException && error.name === "TimeoutError") {
        throw new ProviderError(
          "TIMEOUT",
          `MetaOne gateway route ${capability.key} timed out after ${this.timeoutMs}ms`,
        );
      }
      throw new ProviderError(
        "CONNECTION",
        `MetaOne gateway route ${capability.key} failed: ${error instanceof Error ? error.message : String(error)}`,
      );
    }
  }

  private merge(envelopes: NormalizedEnvelope[], fanoutTruncated: boolean): NormalizedEnvelope {
    const assets = deduplicate(envelopes.flatMap((envelope) => envelope.assets), (asset) => asset.id);
    const relations = deduplicate(
      envelopes.flatMap((envelope) => envelope.relations),
      (relation) => relation.id,
    );
    for (const asset of assets) {
      this.assetTypes.set(asset.id, asset.type);
      const providerId = asset.attributes.providerId;
      if (providerId !== undefined && providerId !== null && providerId !== "") {
        this.providerIds.set(asset.id, String(providerId));
      }
    }
    const incomplete = envelopes.some((envelope) => envelope.complete !== true);
    return {
      assets,
      relations,
      focus: envelopes.find((envelope) => envelope.focus)?.focus,
      total: envelopes.reduce((sum, envelope) => sum + (envelope.total ?? envelope.assets.length), 0),
      complete: envelopes.length > 0 && !incomplete && !fanoutTruncated,
      truncated:
        fanoutTruncated || envelopes.some((envelope) => envelope.truncated || envelope.nextCursor),
      nextCursor: envelopes.find((envelope) => envelope.nextCursor)?.nextCursor,
      snapshotToken: commonValue(envelopes.map((envelope) => envelope.snapshotToken)),
      capturedAt: commonValue(envelopes.map((envelope) => envelope.capturedAt)),
      warnings: [
        ...envelopes.flatMap((envelope) => envelope.warnings),
        ...(fanoutTruncated
          ? [{ code: "gateway_fanout_truncated", message: "Configured route fanout budget was reached." }]
          : []),
      ],
    };
  }

  private providerIdFor(assetId: string): string {
    return this.providerIds.get(assetId) ?? parseProviderId(assetId);
  }
}

function mapArguments(
  binding: GatewayRouteBinding,
  canonicalArguments: Record<string, unknown>,
): Record<string, unknown> {
  const output = { ...(binding.staticArguments ?? {}) };
  for (const [key, value] of Object.entries(canonicalArguments)) {
    if (binding.includeArguments && !binding.includeArguments.includes(key)) continue;
    if (value === undefined || value === null || value === "") continue;
    output[binding.argumentAliases?.[key] ?? key] = value;
  }
  return output;
}

function toSearchParams(values: Record<string, unknown>): URLSearchParams {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(values)) {
    if (Array.isArray(value)) {
      for (const item of value) params.append(key, String(item));
    } else if (typeof value !== "object") {
      params.set(key, String(value));
    }
  }
  return params;
}

function resolvePath(
  path: string,
  values: Record<string, unknown>,
): { path: string; arguments: Record<string, unknown> } {
  const remaining = { ...values };
  const resolved = path.replace(/\{([^}]+)\}/g, (_match, rawName: string) => {
    const name = String(rawName);
    const value = remaining[name];
    if (value === undefined || value === null || value === "") {
      throw new ProviderError("INVALID_REQUEST", `missing gateway path argument: ${name}`);
    }
    delete remaining[name];
    return encodeURIComponent(String(value));
  });
  return { path: resolved, arguments: remaining };
}

function normalizeEnvelope(
  payload: unknown,
  capability: MetaOneEndpointCapability,
  environmentId?: string,
): NormalizedEnvelope {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    throw new ProviderError(
      "INVALID_RESPONSE",
      `MetaOne gateway route ${capability.key} returned a non-object response`,
    );
  }
  const row = payload as Record<string, unknown>;
  if (![...ENVELOPE_KEYS].some((key) => key in row)) {
    throw new ProviderError(
      "INVALID_RESPONSE",
      `MetaOne gateway route ${capability.key} did not return the normalized envelope`,
    );
  }
  const rawAssets = arrayValue(row.assets ?? row.records);
  const rawRelations = arrayValue(row.relations ?? row.edges);
  const assets = rawAssets.map((value) => validateAsset(value, capability, environmentId));
  const relations = rawRelations.map((value) => validateRelation(value, capability));
  const rawFocus = row.focus ?? row.asset;
  const focus = rawFocus ? validateAsset(rawFocus, capability, environmentId) : undefined;
  return {
    assets: focus ? deduplicate([focus, ...assets], (asset) => asset.id) : assets,
    relations,
    focus,
    total: numberValue(row.total ?? row.totalCount),
    complete: booleanValue(row.complete),
    truncated: booleanValue(row.truncated ?? row.hasMore),
    nextCursor: stringValue(row.nextCursor),
    snapshotToken: stringValue(row.snapshotToken),
    capturedAt: stringValue(row.capturedAt),
    warnings: arrayValue(row.warnings).filter(isRecord),
  };
}

function validateAsset(
  value: unknown,
  capability: MetaOneEndpointCapability,
  environmentId?: string,
): Asset {
  const raw = isRecord(value) && isRecord(value.asset) ? value.asset : value;
  if (!isRecord(raw) || !raw.id || !raw.type || !raw.name) {
    throw new ProviderError(
      "INVALID_RESPONSE",
      `MetaOne gateway route ${capability.key} returned an invalid normalized asset`,
    );
  }
  if (!capability.assetTypes.includes(String(raw.type) as Asset["type"])) {
    throw new ProviderError(
      "INVALID_RESPONSE",
      `MetaOne gateway route ${capability.key} returned unexpected asset type ${raw.type}`,
    );
  }
  const evidenceRefs = arrayValue(raw.evidenceRefs).map(String);
  if (evidenceRefs.length === 0) {
    evidenceRefs.push(
      `metaone:${environmentId ?? "unknown"}:${capability.key}:${String(raw.id)}`,
    );
  }
  return {
    id: String(raw.id),
    type: String(raw.type) as Asset["type"],
    code: String(raw.code ?? raw.id),
    name: String(raw.name),
    description: String(raw.description ?? ""),
    aliases: arrayValue(raw.aliases).map(String),
    domain: String(raw.domain ?? ""),
    attributes: isRecord(raw.attributes) ? raw.attributes : {},
    evidenceRefs,
  };
}

function validateRelation(value: unknown, capability: MetaOneEndpointCapability): ContextEdge {
  if (!isRecord(value) || !value.id || !value.sourceId || !value.targetId || !value.predicate) {
    throw new ProviderError(
      "INVALID_RESPONSE",
      `MetaOne gateway route ${capability.key} returned an invalid normalized relation`,
    );
  }
  if (!capability.relations.includes(String(value.predicate))) {
    throw new ProviderError(
      "INVALID_RESPONSE",
      `MetaOne gateway route ${capability.key} returned unexpected relation ${value.predicate}`,
    );
  }
  const evidenceRefs = arrayValue(value.evidenceRefs).map(String);
  if (evidenceRefs.length === 0) {
    evidenceRefs.push(`metaone:unknown:${capability.key}:${String(value.id)}`);
  }
  return {
    id: String(value.id),
    sourceId: String(value.sourceId),
    predicate: String(value.predicate) as ContextEdge["predicate"],
    targetId: String(value.targetId),
    assertionType: "explicit",
    confidence: Number(value.confidence ?? 1),
    status: "verified",
    evidenceRefs,
  };
}

function arrayValue(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function numberValue(value: unknown): number | undefined {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : undefined;
}

function booleanValue(value: unknown): boolean | undefined {
  return typeof value === "boolean" ? value : undefined;
}

function stringValue(value: unknown): string | undefined {
  return value === undefined || value === null || value === "" ? undefined : String(value);
}

function deduplicate<T>(values: T[], key: (value: T) => string): T[] {
  return [...new Map(values.map((value) => [key(value), value])).values()];
}

function commonValue(values: Array<string | undefined>): string | undefined {
  const present = [...new Set(values.filter((value): value is string => Boolean(value)))];
  return present.length === 1 ? present[0] : undefined;
}

function parseProviderType(id: string): string {
  const match = id.match(/(?:^|:)([A-Z][A-Z_]+)(?=:)/);
  return match?.[1] ?? "";
}

function parseProviderId(id: string): string {
  const parts = id.split(":");
  return parts.length >= 3 ? parts.slice(2).join(":") : id;
}

function unavailablePage(code: string, message: string): Record<string, unknown> {
  return {
    records: [],
    assets: [],
    relations: [],
    complete: false,
    truncated: true,
    coverage: coverageFor([], []),
    warnings: [{ code, message }],
  };
}

function normalizeText(value: string): string {
  return value.trim().toLocaleLowerCase().replace(/[\s_-]+/g, "");
}

function searchScore(asset: Asset, query: string): number {
  if (!query) return 1;
  const code = normalizeText(asset.code);
  const name = normalizeText(asset.name);
  const aliases = asset.aliases.map(normalizeText);
  if (code === query) return 1;
  if (name === query) return 0.98;
  if (aliases.includes(query)) return 0.95;
  if (`${code}${name}${aliases.join("")}${normalizeText(asset.description)}`.includes(query)) return 0.7;
  return 0;
}

function searchReasons(asset: Asset, query: string): string[] {
  if (!query) return ["unfiltered"];
  if (normalizeText(asset.code) === query) return ["exact_code"];
  if (normalizeText(asset.name) === query) return ["exact_name"];
  if (asset.aliases.map(normalizeText).includes(query)) return ["exact_alias"];
  return ["partial_text"];
}

function coverageFor(assets: Asset[], relations: ContextEdge[]): Record<string, boolean> {
  const types = new Set(assets.map((asset) => asset.type));
  return {
    metrics: types.has("MEASURE") || types.has("INDICATOR"),
    models:
      types.has("LOGICAL_ENTITY") || types.has("PHYSICAL_TABLE") || types.has("AGGREGATE_MODEL"),
    dimensions:
      types.has("DIMENSION") || types.has("DIMENSION_HIERARCHY") || types.has("DIMENSION_LEVEL"),
    fields:
      types.has("LOGICAL_ATTRIBUTE") ||
      types.has("PHYSICAL_COLUMN") ||
      types.has("DIMENSION_ATTRIBUTE"),
    lineage: relations.some((relation) =>
      ["UPSTREAM_OF", "DERIVES_TO", "TRANSFORMED_BY"].includes(relation.predicate),
    ),
  };
}

function capabilityRevision(value: unknown): string {
  const text = JSON.stringify(value);
  let hash = 2166136261;
  for (let index = 0; index < text.length; index += 1) {
    hash ^= text.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return `gateway-routes-${(hash >>> 0).toString(16).padStart(8, "0")}`;
}
