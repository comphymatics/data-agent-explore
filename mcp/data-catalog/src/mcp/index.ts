import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { createDataCatalogServer } from "./server.js";

const server = createDataCatalogServer();
const transport = new StdioServerTransport();
await server.connect(transport);
console.error("data-catalog MCP server running on stdio");
