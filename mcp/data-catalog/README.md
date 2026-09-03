# MetaOne Environment Metadata MCP

This package is the read-only environment-metadata fixture consumed through
`MetaOneMcpAdapter`. It is not the Enterprise Data Context MCP and it is not an
LLM-facing graph traversal service.

It exposes four capability-negotiated operations:

- `metaone_get_capabilities`
- `metaone_search_assets`
- `metaone_get_asset`
- `metaone_expand_assets`

`src/metaone/endpoints.ts` records the reviewed MetaOne source-interface inventory and
separates `compiler/primary` sources from `serving/verification` or fallback sources.
The authoritative Dimension entry is `/plat/meta/v1/dimensions/`; entity-to-level
mapping, Measure/Indicator relations and `/meta/lineage/v2/queryByModel` provide the
deterministic semantic edges. `/entity/v1/entityColumnRelationById` is retained as a
fast local Semantic Bundle and consistency check, not the Compiler fact authority.

Two transports are available behind the same four MCP tools:

- `HttpDataCatalogProvider` is the local fixture/legacy normalized API and expects
  `/v1/capabilities`, `/v1/assets/search`, `/v1/assets/:id` and `/v1/assets/expand`;
- `MetaOneApiGatewayProvider` routes requests to API-gateway-published MetaOne
  interfaces using a declarative JSON binding.

The gateway transport handles base URL selection, authentication headers, GET/POST,
query/body arguments, parameter aliases, typed stable IDs, bounded fan-out, timeout
and HTTP error classification. It deliberately accepts only a normalized response
envelope; it does not guess fields in undocumented raw MetaOne payloads.

## API gateway configuration

Copy `metaone-gateway.config.example.json` outside the repository and replace every
route method, path and parameter mapping with values verified from the API gateway or
OpenAPI contract. The example is schematic: the source inventory did not include the
HTTP method or request schema for every interface.

Set secrets through the environment, not in the JSON file:

```bash
METAONE_API_GATEWAY_CONFIG=/absolute/path/metaone-gateway.json \
METAONE_API_GATEWAY_BASE_URL=https://gateway.example.com/metaone \
METAONE_API_GATEWAY_TOKEN='replace-at-runtime' \
npm start
```

Supported environment variables:

| Variable | Purpose |
|---|---|
| `METAONE_API_GATEWAY_CONFIG` | Required JSON route-binding file in gateway mode |
| `METAONE_API_GATEWAY_BASE_URL` | Optional override for the JSON `baseUrl` |
| `METAONE_API_GATEWAY_TOKEN` | Runtime credential; never put it in the example file |
| `METAONE_API_GATEWAY_AUTH_HEADER` | Authentication header, default `authorization` |
| `METAONE_API_GATEWAY_AUTH_SCHEME` | Token scheme, default `Bearer`; empty means raw token |
| `METAONE_ENVIRONMENT_ID` | Environment/tenant identity recorded in capabilities |
| `METAONE_API_GATEWAY_TIMEOUT_MS` | Per-route timeout, default 8000 ms |
| `METAONE_API_GATEWAY_MAX_FANOUT` | Maximum routes called by one MCP request, default 8 |

Each configured route refers to an `endpointKey` in `src/metaone/endpoints.ts`.
`includeArguments` is an allow-list, `argumentAliases` maps canonical MCP argument
names to gateway names, and `staticArguments` adds route-specific constants. Assets
must use typed stable IDs such as `metaone:LOGICAL_ENTITY:1001` and should retain the
raw MetaOne ID in `attributes.providerId`.

The gateway or its endpoint-specific adapter must return:

```json
{
  "assets": [
    {
      "id": "metaone:LOGICAL_ENTITY:1001",
      "type": "LOGICAL_ENTITY",
      "code": "Subscriber",
      "name": "用户",
      "description": "当前环境逻辑实体",
      "aliases": ["订户"],
      "domain": "Customer",
      "attributes": { "providerId": "1001" },
      "evidenceRefs": ["metaone:tenant-a:logical-model-list:1001"]
    }
  ],
  "relations": [],
  "total": 1,
  "complete": true,
  "truncated": false,
  "snapshotToken": "metaone-snapshot-7",
  "capturedAt": "2026-09-03T00:00:00Z",
  "warnings": []
}
```

`records` may replace `assets`, `edges` may replace `relations`, and a single read may
also return `focus` or `asset`. Every relation must contain `id`, `sourceId`,
`predicate`, `targetId` and Evidence references. `complete: true` is allowed only when
the authoritative query is known to be complete; missing routes and unknown
completeness remain truncated/partial and never become confirmed absence.

Run the fixture and MCP locally:

```bash
npm test
npm run mock
DATA_CATALOG_BASE_URL=http://127.0.0.1:4100 npm start
```

Keep `livePayloadMappingVerified: false` until real request/response fixtures for the
configured routes pass integration tests. The canonical construction and authority
rules are documented in `../../specs/16-metaone-semantic-construction.md`.
