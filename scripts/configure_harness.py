# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Generate native project MCP/subagent configuration without changing user settings.

Run with `uv run scripts/configure_harness.py`; system Python on macOS may be too old.
All conflicts are checked before writing. Existing unrelated settings are preserved.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
import shutil
import tomllib


REPO = Path(__file__).resolve().parents[1]
SERVER = "enterprise_data_context"
TOOLS = ["data_search", "data_read", "data_expand", "data_source"]
CLIENTS = ("claude-code", "codex", "opencode")
START = "<!-- data-explore integration: start -->"
END = "<!-- data-explore integration: end -->"
DESCRIPTION = "Retrieve evidence-backed enterprise scenarios, metrics, models and fields; return context and explicit gaps to the parent."


def json_text(value):
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def toml_scalar(value):
    if isinstance(value, str):
        if "\n" in value:
            escaped = "".join("\n" if c == "\n" else json.dumps(c, ensure_ascii=False)[1:-1] for c in value)
            return '\"\"\"\n' + escaped + '\"\"\"'
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        return "[" + ", ".join(toml_scalar(v) for v in value) + "]"
    raise TypeError(f"Unsupported TOML scalar: {type(value).__name__}")


def toml_text(value, prefix=()):
    lines = []
    scalars = {k: v for k, v in value.items() if not isinstance(v, dict)}
    if prefix and scalars:
        lines.append("[" + ".".join(toml_scalar(k) for k in prefix) + "]")
    lines.extend(f"{toml_scalar(k)} = {toml_scalar(v)}" for k, v in scalars.items())
    for key, child in value.items():
        if isinstance(child, dict):
            lines.append(toml_text(child, (*prefix, key)).rstrip())
    return "\n".join(lines) + "\n"


def render(client, mode, repo, snapshot, uv, dense="cached", subagent_kind="auto"):
    builtin = subagent_kind == "builtin" or (subagent_kind == "auto" and client != "codex")
    if builtin and client == "codex" and mode != "direct":
        raise ValueError("Codex uses the custom data-explore role in this integration; choose auto or custom")
    args = ["run", "--isolated", "--directory", str(repo)]
    if dense != "disabled":
        args += ["--extra", "dense"]
    args += ["data-context-mcp", str(snapshot)]
    env = ({"DATA_CONTEXT_DENSE_MODEL": "disabled"} if dense == "disabled" else
           {"DATA_CONTEXT_DENSE_LOCAL_ONLY": "1" if dense == "cached" else "0"})
    server = {"command": str(uv), "args": args, "env": env}
    prompt = (REPO / "integrations/harness/data-explore-prompt.md").read_text()
    direct = (REPO / "integrations/harness/direct-instructions.md").read_text()
    files = {}
    if client == "claude-code":
        files[".mcp.json"] = json_text({"mcpServers": {SERVER: {"type": "stdio", **server}}})
        if mode != "direct" and not builtin:
            names = ", ".join(f"mcp__{SERVER}__{t}" for t in TOOLS)
            files[".claude/agents/data-explore.md"] = (
                f"---\nname: data-explore\ndescription: {DESCRIPTION}\n"
                f"tools: {names}\nmodel: inherit\nmaxTurns: 8\n---\n\n" + prompt)
    elif client == "codex":
        codex_server = {**server, "startup_timeout_sec": 120, "tool_timeout_sec": 60,
                        "enabled_tools": TOOLS}
        files[".codex/config.toml"] = toml_text({"mcp_servers": {SERVER: codex_server}})
        if mode != "direct":
            files[".codex/agents/data-explore.toml"] = toml_text({
                "name": "data-explore", "description": DESCRIPTION,
                "sandbox_mode": "read-only", "web_search": "disabled",
                "developer_instructions": prompt,
            })
    else:
        opencode = {
            "$schema": "https://opencode.ai/config.json",
            "mcp": {SERVER: {"type": "local", "command": [str(uv), *args],
                              "environment": env, "enabled": True, "timeout": 120000}},
        }
        if mode != "direct" and builtin:
            # Extend the built-in role without replacing its code-search prompt/tools.
            opencode["agent"] = {"explore": {"permission": {
                f"{SERVER}_{tool}": "allow" for tool in TOOLS}}}
        files["opencode.json"] = json_text(opencode)
        if mode != "direct" and not builtin:
            permissions = '\n'.join(f'  "{SERVER}_{t}": allow' for t in TOOLS)
            files[".opencode/agents/data-explore.md"] = (
                f"---\ndescription: {DESCRIPTION}\nmode: subagent\nsteps: 8\n"
                f'permission:\n  "*": deny\n{permissions}\n---\n\n' + prompt)
    if subagent_kind == "custom":
        role = "Use the custom data-explore subagent."
    else:
        role = ("In Claude Code use the built-in Explore subagent; in OpenCode use the "
                "built-in explore subagent; in Codex use the configured data-explore role.")
    agent_tip = (
        "For multi-entity or multi-aspect enterprise context tasks, delegate retrieval. "
        + role + " The parent must include the following instructions in the delegation "
        "message, because built-in Explore may not load project instructions: use only "
        "the four enterprise_data_context MCP tools for this data task; do not search "
        "files, raw materials, evaluation data or the web. Pass the full question, "
        "explicit entities/aspects and budget. Start with a rich data_search; expand "
        "only missing aspects. Aim for search + one expand, at most four tool calls. "
        "Return query, summary, primary_contexts, evidence-backed findings, missing_context, "
        "sources, candidates, conflicts, warnings, truncated and index_version. "
        "Preserve evidence and UNKNOWN/PARTIAL states; reference assets do not prove "
        "environment deployment. If MCP tools are unavailable, report the missing "
        "capability without substituting filesystem search. The handoff is model-generated, "
        "not Python ContextBundle/Coverage certification. The parent owns the final answer. "
        "For explicit direct-tool requests, call the four MCP tools yourself.\n"
    )
    instructions = direct if mode == "direct" else agent_tip + "\n" + direct
    # Claude reads CLAUDE.md; Codex and OpenCode read AGENTS.md.
    name = "CLAUDE.md" if client == "claude-code" else "AGENTS.md"
    files[name] = START + "\n" + instructions + END + "\n"
    return files


def merge_json(old, new, path=""):
    result = deepcopy(old)
    for key, value in new.items():
        field = f"{path}.{key}" if path else key
        if key not in result:
            result[key] = value
        elif isinstance(value, dict) and isinstance(result[key], dict):
            result[key] = merge_json(result[key], value, field)
        elif result[key] != value:
            raise ValueError(f"Existing setting conflicts: {field}; generate into a staging directory and merge explicitly")
    return result


def merge_file(path, desired):
    if path.is_symlink():
        raise ValueError(f"Refusing to replace a symlink: {path}")
    if not path.exists():
        return desired
    old = path.read_text(encoding="utf-8")
    if old == desired:
        return old
    if path.name in {"CLAUDE.md", "AGENTS.md"}:
        if START in old or END in old:
            if old.count(START) != 1 or old.count(END) != 1 or old.index(START) > old.index(END):
                raise ValueError(f"Malformed managed instruction block: {path}")
            before, tail = old.split(START)
            _, after = tail.split(END)
            return before + desired.rstrip("\n") + after
        return old.rstrip("\n") + "\n\n" + desired
    if path.suffix == ".json":
        merged = merge_json(json.loads(old), json.loads(desired))
        return old if merged == json.loads(old) else json_text(merged)
    if path.name == "config.toml":
        current, wanted = tomllib.loads(old), tomllib.loads(desired)
        # Append a new server table without reformatting or replacing user TOML.
        existing = current.get("mcp_servers", {}).get(SERVER)
        if existing is not None:
            if existing == wanted["mcp_servers"][SERVER]:
                return old
            raise ValueError(f"Existing {SERVER} table conflicts in {path}; merge explicitly")
        combined = old.rstrip("\n") + "\n\n" + desired
        tomllib.loads(combined)
        return combined
    raise ValueError(f"Existing agent file differs: {path}; review and merge explicitly")


def install(target, files, dry_run=False):
    pending = {}
    for relative, desired in files.items():
        path = target / relative
        # Do not follow a configuration directory symlink into user/global settings.
        if any(p.is_symlink() for p in [path, *path.parents] if p == target or target in p.parents):
            raise ValueError(f"Symlink in target configuration path: {path}")
        merged = merge_file(path, desired)
        if not path.exists() or path.read_text(encoding="utf-8") != merged:
            pending[path] = merged
    if not dry_run:
        for path, content in pending.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
    return [str(p) for p in pending]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client", choices=(*CLIENTS, "all"), default="all")
    parser.add_argument("--mode", choices=("direct", "subagent", "both"), default="both",
                        help="subagent/both configure MCP and delegation; this is routing guidance, not parent tool isolation")
    parser.add_argument("--subagent-kind", choices=("auto", "builtin", "custom"), default="auto",
                        help="auto: built-in Explore for Claude Code/OpenCode, custom role for Codex")
    parser.add_argument("--target", type=Path, default=REPO, help="Target harness project (not user/global settings)")
    parser.add_argument("--repo", type=Path, default=REPO, help="Retrieval service checkout")
    parser.add_argument("--snapshot", type=Path, help="Published context root; defaults to REPO/generated")
    parser.add_argument("--uv", default=shutil.which("uv"), help="Absolute uv executable")
    parser.add_argument("--dense", choices=("cached", "download", "disabled"), default="cached")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    repo = args.repo.expanduser().resolve()
    target = args.target.expanduser().resolve()
    snapshot = (args.snapshot or repo / "generated").expanduser().resolve()
    if not args.uv or not Path(args.uv).is_file():
        parser.error("uv executable not found; supply --uv /absolute/path/to/uv")
    if not (repo / "pyproject.toml").is_file() or not (snapshot / "latest.json").is_file():
        parser.error("Need a service checkout and a published snapshot containing latest.json")
    if args.client in ("opencode", "all") and (target / "opencode.jsonc").exists():
        parser.error("Existing opencode.jsonc: generate into a staging directory and merge into that file")
    files = {}
    try:
        for client in CLIENTS if args.client == "all" else [args.client]:
            files.update(render(client, args.mode, repo, snapshot, Path(args.uv).absolute(), args.dense, args.subagent_kind))
    except ValueError as exc:
        parser.error(str(exc))
    if "CLAUDE.md" in files and ("AGENTS.md" in files or (target / "AGENTS.md").is_file()):
        files["CLAUDE.md"] = files["CLAUDE.md"].replace(START + "\n", START + "\n@AGENTS.md\n\n", 1)
    try:
        changed = install(target, files, args.dry_run)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    print(json_text({"dry_run": args.dry_run, "target": str(target), "changed": changed}))


if __name__ == "__main__":
    main()
