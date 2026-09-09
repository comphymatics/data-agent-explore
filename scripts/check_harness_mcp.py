# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Check the exact native MCP launch configuration without calling any LLM."""
from __future__ import annotations

import argparse
from collections import deque
import json
import os
from pathlib import Path
from queue import Queue, Empty
import subprocess
from threading import Thread
import time
import tomllib

SERVER = "enterprise_data_context"
TOOLS = ["data_search", "data_read", "data_expand", "data_source"]


def launch_spec(path):
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".toml":
        value = tomllib.loads(text)["mcp_servers"][SERVER]
    else:
        config = json.loads(text)
        if "mcpServers" in config:
            value = config["mcpServers"][SERVER]
        else:
            value = config["mcp"][SERVER]
    command = value["command"]
    argv = command if isinstance(command, list) else [command, *value.get("args", [])]
    return argv, value.get("env", value.get("environment", {}))


def check(path, query="高铁场景", timeout=120):
    argv, environment = launch_spec(path)
    started = time.monotonic()
    process = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True,
                               env={**os.environ, **environment})
    lines = Queue()
    errors = deque(maxlen=15)
    def read_stdout():
        for line in process.stdout:
            lines.put(line)
        lines.put(None)
    def read_stderr():
        for line in process.stderr:
            errors.append(line.rstrip())
    Thread(target=read_stdout, daemon=True).start()
    Thread(target=read_stderr, daemon=True).start()
    request_id = 0
    def send(message):
        process.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
        process.stdin.flush()
    def request(method, params):
        nonlocal request_id
        request_id += 1
        send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        deadline = time.monotonic() + timeout
        while True:
            try:
                line = lines.get(timeout=max(.001, deadline - time.monotonic()))
            except Empty:
                raise RuntimeError(f"{method} timed out after {timeout}s") from None
            if line is None:
                raise RuntimeError(f"MCP exited during {method}: " + "\n".join(errors))
            response = json.loads(line)
            if response.get("id") != request_id:
                if time.monotonic() >= deadline:
                    raise RuntimeError(f"{method} response deadline exceeded")
                continue
            if "error" in response:
                raise RuntimeError(str(response["error"]))
            return response["result"]
    def call(name, arguments):
        result = request("tools/call", {"name": name, "arguments": arguments})
        if result.get("isError"):
            raise RuntimeError(f"{name} failed: {result.get('content')}")
        if "structuredContent" in result:
            return result["structuredContent"]
        return json.loads(next(x["text"] for x in result["content"] if x["type"] == "text"))
    try:
        initialized = request("initialize", {
            "protocolVersion": "2025-06-18", "capabilities": {},
            "clientInfo": {"name": "data-explore-harness-check", "version": "1"},
        })
        send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        names = [t["name"] for t in request("tools/list", {})["tools"]]
        if set(names) != set(TOOLS):
            raise RuntimeError(f"Expected exactly four Context tools, got {names}")
        search = call("data_search", {"query": query, "mode": "auto", "top_k": 3,
                      "bundle_k": 3, "token_budget": 2000, "read_content": "auto"})
        calls = ["data_search"]
        hits = search["contexts"]
        if hits:
            selected = hits[0]["path"]
            call("data_read", {"path": selected, "level": "L1"})
            call("data_expand", {"paths": [selected], "expand": ["hierarchy", "conflicts"],
                                 "top_k": 3, "token_budget": 1500})
            call("data_source", {"path": selected})
            calls += TOOLS[1:]
        return {"status": "passed" if hits else "partial_no_hits", "config": str(path),
                "validation_scope": "native launch command + MCP protocol + real snapshot tools; no host LLM delegation",
                "server": initialized["serverInfo"], "tools": names, "calls": calls,
                "query": query, "hit_count": len(hits), "hit_names": [h["name"] for h in hits],
                "index_version": search.get("index_version"),
                "retrieval_version": search.get("retrieval_version"),
                "warnings": search.get("warnings", []),
                "elapsed_seconds": round(time.monotonic() - started, 2)}
    finally:
        process.stdin.close()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--query", default="高铁场景")
    parser.add_argument("--timeout", type=float, default=120)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("timeout must be positive")
    result = check(args.config.resolve(), args.query, args.timeout)
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
