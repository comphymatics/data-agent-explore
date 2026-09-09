For enterprise scenarios, metrics, models, fields, grain, lineage and business mappings,
use the enterprise_data_context MCP server. Start with data_search using mode="auto",
top_k=5, bundle_k=6, token_budget=4000 and read_content="auto". Search includes rich
context; avoid reading every hit again. Use data_expand for specific missing aspects,
data_read for selected detailed sections, and data_source for provenance checks.
Keep evidence, index versions, missing context, candidates, conflicts and truncation.
An empty result does not prove absence; a Reference model does not prove deployment.
The service is read-only and exposes four tools. It does not automatically invoke the
Python ExploreAgent or load config/llm-inference.json. The host agent supplies the LLM.
