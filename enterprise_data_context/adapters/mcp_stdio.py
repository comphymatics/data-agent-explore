from __future__ import annotations

import argparse
import json
import sys

from enterprise_data_context.runtime import load_runtime
from enterprise_data_context.tools import DataContextTools


PROTOCOL_VERSION = "2025-11-25"
SERVER_INFO = {
    "name": "enterprise-data-context",
    "title": "Enterprise Data Context",
    "version": "1.0.0",
    "description": "Read-only Rich Context Page retrieval for Explore agents.",
}


TOOL_DEFINITIONS = [
    {
        "name": "data_search",
        "title": "Search managed context bundle",
        "description": (
            "Search Rich Context Pages and complete a bounded bundle with direct typed "
            "references and derived backrefs. Supports token budgets and cross-round deduplication."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "minLength": 1},
                "mode": {"enum": ["auto", "direct", "hierarchical", "hybrid"], "default": "auto"},
                "hierarchy": {"enum": ["analysis", "domain", "asset"]},
                "scope": {
                    "type": "object",
                    "description": "Keyed retrieval scope; governed model facets use formal ODS/SDL/ODI/ADS values.",
                    "properties": {
                        "layer": {"enum": ["ODS", "SDL", "ODI", "ADS"]},
                        "topic_domain": {"type": "string"},
                        "topic": {"type": "string"},
                        "technology": {"type": "string"},
                        "scenario": {"type": "string"},
                        "analysis_purpose": {"type": "string"},
                        "semantic_role": {"type": "string"},
                        "scenario_kind": {"enum": ["APP_FEATURE", "MODELING_ANALYSIS"]},
                        "application": {"type": "string"},
                        "symbol": {"type": "string"},
                    },
                    "additionalProperties": False,
                },
                "types": {"type": "array", "items": {"type": "string"}},
                "top_k": {"type": "integer", "minimum": 1, "default": 8},
                "bundle_k": {"type": "integer", "minimum": 1},
                "token_budget": {"type": "integer", "minimum": 1},
                "seen_context_ids": {"type": "array", "items": {"type": "string"}},
                "read_content": {"enum": ["L0", "L1", "auto"]},
                "max_per_type": {"type": "integer", "minimum": 1},
                "intent": {"enum": ["generic", "metric_to_models", "analysis_data_requirement", "model_understanding", "impact_analysis"]},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
    {
        "name": "data_read",
        "title": "Read a Rich Context Page",
        "description": (
            "Read one context or data://views aggregate page at L0, L1, or selected L2 sections. A hierarchy:// "
            "path returns the derived classification node and its browse context."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "minLength": 1},
                "level": {"enum": ["L0", "L1", "L2"], "default": "L1"},
                "sections": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["path"],
            "additionalProperties": False,
        },
    },
    {
        "name": "data_expand",
        "title": "Expand focused context sections",
        "description": (
            "Expand fields, grain, lineage, mappings, hierarchy, parents, children, related "
            "rich relation summaries, candidates, conflicts, evidence, or the association report. "
            "Optional query searches Field/Attribute/Formula/Counter/JoinKey elements inside "
            "selected pages and returns their parent Rich Context Page and evidence. "
            "Use fields, attributes, formula, counters, join_keys, or elements in expand."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "paths": {"type": "array", "minItems": 1, "items": {"type": "string"}},
                "expand": {"type": "array", "minItems": 1, "items": {"type": "string"}},
                "top_k": {"type": "integer", "minimum": 1, "default": 20},
                "query": {"type": "string", "minLength": 1},
                "intent": {"enum": ["generic", "metric_to_models", "analysis_data_requirement", "model_understanding", "impact_analysis"]},
                "token_budget": {"type": "integer", "minimum": 1},
            },
            "required": ["paths", "expand"],
            "additionalProperties": False,
        },
    },
    {
        "name": "data_source",
        "title": "Read context evidence",
        "description": "Return source locations and provenance for a context or section.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "minLength": 1},
                "section": {"type": "string"},
            },
            "required": ["path"],
            "additionalProperties": False,
        },
    },
]


class DataContextMCPServer:
    """Dependency-free MCP stdio adapter over the four platform-neutral tools."""

    def __init__(self, tools):
        self.tools = tools if isinstance(tools, DataContextTools) else DataContextTools(tools)
        self.initialized = False

    def handle(self, message):
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
            return _error(None, -32600, "Invalid Request")

        method = message.get("method")
        request_id = message.get("id")
        if request_id is None:
            if method == "notifications/initialized":
                self.initialized = True
            return None

        if method == "initialize":
            requested = message.get("params", {}).get("protocolVersion")
            negotiated = requested if requested in {"2025-06-18", PROTOCOL_VERSION} else PROTOCOL_VERSION
            return _result(request_id, {
                "protocolVersion": negotiated,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": SERVER_INFO,
                "instructions": (
                    "This is a read-only Context Engine. Prefer data_search, then use focused "
                    "data_read/data_expand/data_source calls; do not traverse graph nodes manually."
                ),
            })
        if method == "ping":
            return _result(request_id, {})
        if not self.initialized:
            return _error(request_id, -32002, "Server not initialized")
        if method == "tools/list":
            return _result(request_id, {"tools": TOOL_DEFINITIONS})
        if method == "tools/call":
            params = message.get("params") or {}
            name = params.get("name")
            if name not in self.tools.ALLOWED:
                return _error(request_id, -32602, f"Unknown tool: {name}")
            try:
                value = self.tools.call(name, params.get("arguments") or {})
            except (KeyError, TypeError, ValueError) as exc:
                return _result(request_id, {
                    "content": [{"type": "text", "text": str(exc)}],
                    "isError": True,
                })
            structured = value if isinstance(value, dict) else {"result": value}
            return _result(request_id, {
                "content": [{
                    "type": "text",
                    "text": json.dumps(value, ensure_ascii=False, separators=(",", ":")),
                }],
                "structuredContent": structured,
                "isError": False,
            })
        return _error(request_id, -32601, f"Method not found: {method}")


def serve_stdio(server, input_stream=None, output_stream=None):
    input_stream = input_stream or sys.stdin
    output_stream = output_stream or sys.stdout
    for line in input_stream:
        try:
            message = json.loads(line)
            response = server.handle(message)
        except json.JSONDecodeError:
            response = _error(None, -32700, "Parse error")
        except Exception as exc:
            response = _error(None, -32603, f"Internal error: {exc}")
        if response is not None:
            output_stream.write(json.dumps(response, ensure_ascii=False, separators=(",", ":")) + "\n")
            output_stream.flush()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Serve Enterprise Data Context over MCP stdio")
    parser.add_argument("context_root", help="Generated context root containing latest.json")
    parser.add_argument("--index-version", help="Pin an immutable IndexVersion")
    args = parser.parse_args(argv)
    runtime = load_runtime(args.context_root, index_version=args.index_version)
    serve_stdio(DataContextMCPServer(runtime.retrieval))


def _result(request_id, value):
    return {"jsonrpc": "2.0", "id": request_id, "result": value}


def _error(request_id, code, message):
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message},
    }


if __name__ == "__main__":
    main()
