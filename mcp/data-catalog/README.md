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

The checked-in HTTP provider expects a normalized gateway with `/v1/capabilities`,
`/v1/assets/search`, `/v1/assets/:id` and `/v1/assets/expand`. It deliberately does not
guess MetaOne request methods, authentication headers or raw response fields because
the interface list contains no real request/response samples. Capture those samples,
then implement their mapping behind `DataCatalogProvider` without changing the MCP
tools or Explore contracts.

Run the fixture and MCP locally:

```bash
npm test
npm run mock
DATA_CATALOG_BASE_URL=http://127.0.0.1:4100 npm start
```

The fixture capability response sets `livePayloadMappingVerified: false`; do not use
it as evidence of production MetaOne compatibility. The canonical construction and
authority rules are documented in `../../specs/16-metaone-semantic-construction.md`.
