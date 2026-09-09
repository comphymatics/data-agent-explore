<!-- data-explore integration: start -->
@AGENTS.md

For multi-entity or multi-aspect enterprise context tasks, delegate retrieval. In Claude Code use the built-in Explore subagent; in OpenCode use the built-in explore subagent; in Codex use the configured data-explore role. The parent must include the following instructions in the delegation message, because built-in Explore may not load project instructions: use only the four enterprise_data_context MCP tools for this data task; do not search files, raw materials, evaluation data or the web. Pass the full question, explicit entities/aspects and budget. Start with a rich data_search; expand only missing aspects. Aim for search + one expand, at most four tool calls. Return query, summary, primary_contexts, evidence-backed findings, missing_context, sources, candidates, conflicts, warnings, truncated and index_version. Preserve evidence and UNKNOWN/PARTIAL states; reference assets do not prove environment deployment. If MCP tools are unavailable, report the missing capability without substituting filesystem search. The handoff is model-generated, not Python ContextBundle/Coverage certification. The parent owns the final answer. For explicit direct-tool requests, call the four MCP tools yourself.

For enterprise scenarios, metrics, models, fields, grain, lineage and business mappings,
use the enterprise_data_context MCP server. Start with data_search using mode="auto",
top_k=5, bundle_k=6, token_budget=4000 and read_content="auto". Search includes rich
context; avoid reading every hit again. Use data_expand for specific missing aspects,
data_read for selected detailed sections, and data_source for provenance checks.
Keep evidence, index versions, missing context, candidates, conflicts and truncation.
An empty result does not prove absence; a Reference model does not prove deployment.
The service is read-only and exposes four tools. It does not automatically invoke the
Python ExploreAgent or load config/llm-inference.json. The host agent supplies the LLM.
<!-- data-explore integration: end -->
