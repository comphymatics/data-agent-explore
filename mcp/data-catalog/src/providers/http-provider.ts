import type { ExpandInput, SearchInput } from "../domain/types.js";
import { ProviderError, type DataCatalogProvider } from "./provider.js";

export interface HttpProviderOptions {
  baseUrl: string;
  timeoutMs?: number;
}

export class HttpDataCatalogProvider implements DataCatalogProvider {
  private readonly baseUrl: string;
  private readonly timeoutMs: number;

  constructor(options: HttpProviderOptions) {
    this.baseUrl = options.baseUrl.replace(/\/+$/, "");
    this.timeoutMs = options.timeoutMs ?? 5000;
  }

  private async get<T>(path: string): Promise<T> {
    try {
      const response = await fetch(`${this.baseUrl}${path}`, {
        signal: AbortSignal.timeout(this.timeoutMs),
        headers: { accept: "application/json" },
      });
      const body = await response.json().catch(() => undefined);
      if (!response.ok) {
        throw new ProviderError(
          response.status === 404 ? "NOT_FOUND" : "PROVIDER_ERROR",
          `metadata provider returned HTTP ${response.status}`,
          response.status,
        );
      }
      if (!body || typeof body !== "object") {
        throw new ProviderError("INVALID_RESPONSE", "metadata provider returned a non-object response");
      }
      return body as T;
    } catch (error) {
      if (error instanceof ProviderError) throw error;
      if (error instanceof DOMException && error.name === "TimeoutError") {
        throw new ProviderError("TIMEOUT", `metadata provider timed out after ${this.timeoutMs}ms`);
      }
      throw new ProviderError(
        "CONNECTION",
        `cannot connect to metadata provider at ${this.baseUrl}: ${error instanceof Error ? error.message : String(error)}`,
      );
    }
  }

  getCapabilities(): Promise<Record<string, unknown>> {
    return this.get("/v1/capabilities");
  }

  searchAssets(input: SearchInput): Promise<Record<string, unknown>> {
    const params = new URLSearchParams({ q: input.query });
    for (const type of input.types ?? []) params.append("type", type);
    if (input.domain) params.set("domain", input.domain);
    if (input.limit) params.set("limit", String(input.limit));
    if (input.cursor) params.set("cursor", input.cursor);
    return this.get(`/v1/assets/search?${params.toString()}`);
  }

  getAssetContext(id: string, depth = 2, maxNodes = 50): Promise<Record<string, unknown>> {
    const params = new URLSearchParams({ depth: String(depth), maxNodes: String(maxNodes) });
    return this.get(`/v1/assets/${encodeURIComponent(id)}?${params.toString()}`);
  }

  expandAssets(input: ExpandInput): Promise<Record<string, unknown>> {
    const params = new URLSearchParams();
    for (const id of input.ids) params.append("id", id);
    for (const relation of input.relations ?? []) params.append("relation", relation);
    if (input.limit) params.set("limit", String(input.limit));
    return this.get(`/v1/assets/expand?${params.toString()}`);
  }
}
