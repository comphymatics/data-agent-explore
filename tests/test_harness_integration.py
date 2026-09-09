"""Installer preservation and native configuration contract checks; no LLM calls."""
import importlib.util
import json
from pathlib import Path
import sys

import pytest
import yaml

if sys.version_info < (3, 11):
    pytest.skip("The standalone harness installer requires Python 3.11+ via uv", allow_module_level=True)
import tomllib

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("configure_harness", ROOT / "scripts/configure_harness.py")
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


def rendered(client, mode="both", subagent_kind="auto"):
    # Spaces, quotes and non-ASCII paths must survive each native config format.
    return installer.render(client, mode, Path('/tmp/项目 with "quotes"'),
                            Path('/tmp/context snapshot'), Path('/tmp/bin/uv'), subagent_kind=subagent_kind)


def frontmatter(text):
    return yaml.safe_load(text.split("---", 2)[1])


@pytest.mark.parametrize("client", installer.CLIENTS)
def test_native_commands_and_agent_restrictions(client):
    files = rendered(client, subagent_kind="custom")
    if client == "claude-code":
        server = json.loads(files[".mcp.json"])["mcpServers"][installer.SERVER]
        agent = frontmatter(files[".claude/agents/data-explore.md"])
        assert agent["model"] == "inherit"
        assert set(agent["tools"].split(", ")) == {
            f"mcp__{installer.SERVER}__{t}" for t in installer.TOOLS}
    elif client == "codex":
        server = tomllib.loads(files[".codex/config.toml"])["mcp_servers"][installer.SERVER]
        agent = tomllib.loads(files[".codex/agents/data-explore.toml"])
        assert agent["sandbox_mode"] == "read-only"
        assert agent["web_search"] == "disabled" and "model" not in agent
        assert server["enabled_tools"] == installer.TOOLS
    else:
        server = json.loads(files["opencode.json"])["mcp"][installer.SERVER]
        agent = frontmatter(files[".opencode/agents/data-explore.md"])
        assert agent["mode"] == "subagent" and "model" not in agent
        assert agent["permission"] == {"*": "deny", **{
            f"{installer.SERVER}_{t}": "allow" for t in installer.TOOLS}}
    args = server.get("args", server["command"])
    assert args[args.index("--directory") + 1] == '/tmp/项目 with "quotes"'
    assert args[-1] == '/tmp/context snapshot'


@pytest.mark.parametrize("client", installer.CLIENTS)
def test_direct_mode_does_not_create_subagent(client):
    assert not any("/agents/" in p for p in rendered(client, "direct"))


def test_existing_settings_and_architecture_rules_survive(tmp_path):
    (tmp_path / ".mcp.json").write_text(json.dumps({"mcpServers": {"other": {"command": "other"}}}))
    (tmp_path / "AGENTS.md").write_text("# Existing architecture\nDo not change production contracts.\n")
    (tmp_path / ".codex").mkdir()
    (tmp_path / ".codex/config.toml").write_text('# Keep comments\nmodel = "my-model"\n[agents]\nenabled = true\n')
    files = {}
    for client in installer.CLIENTS:
        files.update(rendered(client))
    installer.install(tmp_path, files)
    assert json.loads((tmp_path / ".mcp.json").read_text())["mcpServers"]["other"] == {"command": "other"}
    text = (tmp_path / ".codex/config.toml").read_text()
    assert text.startswith('# Keep comments\nmodel = "my-model"')
    assert tomllib.loads(text)["agents"]["enabled"] is True
    assert (tmp_path / "AGENTS.md").read_text().startswith("# Existing architecture\nDo not change production contracts.\n")
    assert installer.install(tmp_path, files) == []


def test_conflict_is_detected_before_any_writes(tmp_path):
    (tmp_path / "opencode.json").write_text(json.dumps({"mcp": {installer.SERVER: {"type": "remote"}}}))
    before = (tmp_path / "opencode.json").read_bytes()
    files = {**rendered("claude-code"), **rendered("opencode")}
    with pytest.raises(ValueError, match="conflicts"):
        installer.install(tmp_path, files)
    assert (tmp_path / "opencode.json").read_bytes() == before
    assert not (tmp_path / ".mcp.json").exists()
    assert not (tmp_path / ".claude").exists()


def test_dry_run_and_symlink_do_not_write(tmp_path):
    files = rendered("claude-code", subagent_kind="custom")
    assert installer.install(tmp_path, files, dry_run=True)
    assert not (tmp_path / ".mcp.json").exists()
    elsewhere = tmp_path / "global"
    elsewhere.mkdir()
    (tmp_path / ".claude").symlink_to(elsewhere, target_is_directory=True)
    with pytest.raises(ValueError, match="Symlink"):
        installer.install(tmp_path, files)
    assert not (tmp_path / ".mcp.json").exists()
    assert list(elsewhere.iterdir()) == []


def test_cli_is_idempotent_in_new_project_and_imports_architecture(tmp_path, capsys):
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    (snapshot / "latest.json").write_text('{}')
    target = tmp_path / "consumer"
    args = ["--client", "all", "--target", str(target), "--snapshot", str(snapshot),
            "--uv", sys.executable]
    installer.main(args)
    assert json.loads(capsys.readouterr().out)["changed"]
    assert "@AGENTS.md" in (target / "CLAUDE.md").read_text()
    installer.main(args)
    assert json.loads(capsys.readouterr().out)["changed"] == []


@pytest.mark.parametrize("client", ["claude-code", "opencode"])
def test_default_reuses_builtin_and_passes_instructions_in_task(client):
    files = rendered(client)
    assert not any("/agents/" in p for p in files)
    instructions = files["CLAUDE.md" if client == "claude-code" else "AGENTS.md"]
    assert "include the following instructions in the delegation message" in instructions
    assert "built-in Explore" in instructions
    if client == "opencode":
        overlay = json.loads(files["opencode.json"])["agent"]["explore"]
        assert overlay == {"permission": {f"{installer.SERVER}_{t}": "allow" for t in installer.TOOLS}}


def test_opencode_builtin_overlay_preserves_existing_settings(tmp_path):
    (tmp_path / "opencode.json").write_text(json.dumps({"agent": {"explore": {
        "model": "existing-model", "permission": {"edit": "deny"}}}}))
    installer.install(tmp_path, rendered("opencode"))
    agent = json.loads((tmp_path / "opencode.json").read_text())["agent"]["explore"]
    assert agent["model"] == "existing-model"
    assert agent["permission"]["edit"] == "deny"
    assert agent["permission"][f"{installer.SERVER}_data_search"] == "allow"
