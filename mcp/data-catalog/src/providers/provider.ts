import type { AssetType, ExpandInput, SearchInput } from "../domain/types.js";

export interface DataCatalogProvider {
  getCapabilities(): Promise<Record<string, unknown>>;
  searchAssets(input: SearchInput): Promise<Record<string, unknown>>;
  getAssetContext(id: string, depth?: number, maxNodes?: number): Promise<Record<string, unknown>>;
  expandAssets(input: ExpandInput): Promise<Record<string, unknown>>;
}

export class ProviderError extends Error {
  constructor(
    readonly category:
      | "TIMEOUT"
      | "CONNECTION"
      | "NOT_FOUND"
      | "INVALID_RESPONSE"
      | "PROVIDER_ERROR",
    message: string,
    readonly status?: number,
  ) {
    super(message);
    this.name = "ProviderError";
  }
}

export function parseAssetTypes(values: string[] | undefined): AssetType[] | undefined {
  return values?.length ? (values as AssetType[]) : undefined;
}
