# Explore Agent
Understand query -> infer scope/intent -> search bundle -> joint structured reasoning -> coverage check -> focused expansion -> final Context Bundle.
Explore does not perform final model design or SQL generation.

Explore orchestrates two read paths without merging their stores: MetaOne-first
environment lookup for real available assets, followed by Reference Context semantic
enrichment and governed fallback. It consumes a stable Environment Binding contract;
it does not depend on raw MetaOne MCP tool names or response fields.
