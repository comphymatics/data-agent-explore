# LEGACY / NON-HEADLINE EVALUATION — official entry: python -m evaluation
from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from .base import RetrievalAdapter
from ..models import RetrievalResult


FINAL_IDS_RE = re.compile(r"EVIDENCE_IDS_JSON\s*=\s*(\[[^\r\n]*\])")
TASK_ID_RE = re.compile(r'<task id="([^"]+)"')


class OpenCodeExploreAdapter(RetrievalAdapter):
    name = "opencode_explore"

    def __init__(self, config: dict[str, Any], corpus_dir: Path):
        super().__init__(config, corpus_dir)
        self.command = str(config.get("command", "opencode"))
        self.model = str(config.get("model", "opencode/big-pickle"))
        self.primary_agent = str(config.get("primary_agent", "plan"))
        self.timeout_seconds = int(config.get("timeout_seconds", 240))
        self.pure = bool(config.get("pure", True))
        self._execution_temp: tempfile.TemporaryDirectory[str] | None = None
        self._execution_dir: Path | None = None
        self._execution_digest: str | None = None
        if self.primary_agent == "explore":
            raise ValueError(
                "OpenCode explore is a subagent and cannot be passed as the primary --agent; "
                "use a primary orchestrator such as plan and require a traced explore task"
            )

    def _reset_execution_copy(self) -> None:
        if self._execution_temp is not None:
            self._execution_temp.cleanup()
        self._execution_temp = None
        self._execution_dir = None
        self._execution_digest = None

    def _get_execution_dir(self) -> Path:
        if self._execution_dir is None:
            self._execution_temp = tempfile.TemporaryDirectory(prefix="opencode-explore-eval-")
            self._execution_dir = Path(self._execution_temp.name) / "evidence-pages"
            shutil.copytree(self.corpus_dir, self._execution_dir)
            self._execution_digest = self._corpus_digest(self._execution_dir)
        return self._execution_dir

    @staticmethod
    def _corpus_digest(directory: Path) -> str:
        digest = hashlib.sha256()
        for path in sorted(item for item in directory.rglob("*") if item.is_file()):
            digest.update(path.relative_to(directory).as_posix().encode("utf-8"))
            digest.update(b"\0")
            digest.update(path.read_bytes())
            digest.update(b"\0")
        return digest.hexdigest()

    def preflight(self) -> dict[str, Any]:
        executable = shutil.which(self.command)
        if not executable:
            raise RuntimeError(f"OpenCode command not found: {self.command}")
        if not self.corpus_dir.is_dir():
            raise RuntimeError(f"corpus directory not found: {self.corpus_dir}")
        version = subprocess.run(
            [executable, "--version"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        if version.returncode != 0:
            raise RuntimeError(f"OpenCode version check failed: {version.stderr.strip()}")
        return {
            "command": executable,
            "version": version.stdout.strip(),
            "model": self.model,
            "primary_agent": self.primary_agent,
            "corpus_dir": str(self.corpus_dir),
        }

    def _prompt(self, query: str, token_budget: int) -> str:
        return (
            "You are an evaluation orchestrator. You MUST invoke the built-in explore subagent "
            "exactly once. Ask it to search ONLY the files under the current working directory. "
            "It must not inspect parent directories. The corpus files contain explicit "
            "EVIDENCE_ID markers. Find evidence that directly supports the following enterprise "
            f"data-context query: {query}\n"
            f"The retrieval context budget is {token_budget} tokens. Prefer required evidence and "
            "avoid candidates or unrelated background. The explore subagent must return only IDs "
            "that occur verbatim after EVIDENCE_ID markers. After the subagent returns, output "
            "exactly one final line in this form and no explanation: "
            'EVIDENCE_IDS_JSON=["ev-example"]'
        )

    @staticmethod
    def _parse_events(stdout: str) -> tuple[list[dict[str, Any]], list[str], int, list[str]]:
        events: list[dict[str, Any]] = []
        child_ids: list[str] = []
        parent_tokens = 0
        final_texts: list[str] = []
        for raw in stdout.splitlines():
            try:
                event = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict):
                continue
            events.append(event)
            part = event.get("part", {})
            if event.get("type") == "step_finish":
                total = part.get("tokens", {}).get("total")
                if isinstance(total, (int, float)):
                    parent_tokens += int(total)
            if event.get("type") == "text" and isinstance(part.get("text"), str):
                final_texts.append(part["text"])
            if event.get("type") == "tool_use" and part.get("tool") == "task":
                state = part.get("state", {})
                task_input = state.get("input", {})
                subtype = task_input.get("subagent_type") or task_input.get("agent")
                if subtype != "explore":
                    continue
                metadata = state.get("metadata", {})
                child_id = metadata.get("sessionId") or metadata.get("sessionID")
                if not child_id and isinstance(state.get("output"), str):
                    match = TASK_ID_RE.search(state["output"])
                    child_id = match.group(1) if match else None
                if child_id:
                    child_ids.append(str(child_id))
        return events, list(dict.fromkeys(child_ids)), parent_tokens, final_texts

    def _export_session_tokens(self, session_id: str, execution_dir: Path) -> tuple[int | None, str | None]:
        try:
            completed = subprocess.run(
                [self.command, "export", session_id],
                cwd=execution_dir,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return None, str(exc)
        if completed.returncode != 0:
            return None, completed.stderr.strip() or f"export exited {completed.returncode}"
        start = completed.stdout.find("{")
        if start < 0:
            return None, "OpenCode export did not return JSON"
        try:
            payload = json.loads(completed.stdout[start:])
        except json.JSONDecodeError as exc:
            return None, f"invalid OpenCode export JSON: {exc}"
        tokens = payload.get("info", {}).get("tokens", {})
        cache = tokens.get("cache", {})
        values = [
            tokens.get("input", 0),
            tokens.get("output", 0),
            tokens.get("reasoning", 0),
            cache.get("read", 0),
            cache.get("write", 0),
        ]
        if not all(isinstance(value, (int, float)) for value in values):
            return None, "OpenCode export token fields were incomplete"
        return sum(int(value) for value in values), None

    @staticmethod
    def _parse_final_ids(texts: list[str]) -> tuple[list[str], str | None]:
        for text in reversed(texts):
            match = FINAL_IDS_RE.search(text)
            if not match:
                continue
            try:
                value = json.loads(match.group(1))
            except json.JSONDecodeError as exc:
                return [], f"invalid EVIDENCE_IDS_JSON: {exc}"
            if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
                return [], "EVIDENCE_IDS_JSON must be an array of strings"
            return list(dict.fromkeys(item.lower() for item in value)), None
        return [], "final EVIDENCE_IDS_JSON line not found"

    def retrieve(
        self,
        case: dict[str, Any],
        query: str,
        query_id: str,
        repeat: int,
    ) -> RetrievalResult:
        execution_dir = self._get_execution_dir()
        before = self._execution_digest
        result = self._retrieve_in_dir(case, query, query_id, repeat, execution_dir)
        after = self._corpus_digest(execution_dir)
        if before != after:
            result.valid = False
            mutation_error = "OpenCode modified its private retrieval-corpus copy"
            result.error = f"{result.error}; {mutation_error}" if result.error else mutation_error
            result.diagnostics["corpus_mutated"] = True
            self._reset_execution_copy()
        else:
            result.diagnostics["corpus_mutated"] = False
        return result

    def _retrieve_in_dir(
        self,
        case: dict[str, Any],
        query: str,
        query_id: str,
        repeat: int,
        execution_dir: Path,
    ) -> RetrievalResult:
        command = [self.command, "run"]
        if self.pure:
            command.append("--pure")
        command.extend(
            [
                "--format",
                "json",
                "--model",
                self.model,
                "--agent",
                self.primary_agent,
                "--dir",
                str(execution_dir),
                self._prompt(query, int(case["context_token_budget"])),
            ]
        )
        started = time.monotonic()
        try:
            completed = subprocess.run(
                command,
                cwd=execution_dir,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            partial_stdout = exc.stdout or ""
            if isinstance(partial_stdout, bytes):
                partial_stdout = partial_stdout.decode("utf-8", errors="replace")
            events, child_ids, parent_tokens, final_texts = self._parse_events(partial_stdout)
            evidence_ids, _ = self._parse_final_ids(final_texts)
            child_tokens = 0
            token_errors: list[str] = []
            for child_id in child_ids:
                value, error = self._export_session_tokens(child_id, execution_dir)
                if value is not None:
                    child_tokens += value
                if error:
                    token_errors.append(error)
            return RetrievalResult(
                system=self.name,
                case_id=case["case_id"],
                query_id=query_id,
                query=query,
                repeat=repeat,
                evidence_ids=evidence_ids,
                query_tokens=(parent_tokens + child_tokens) or None,
                token_details={
                    "parent_model_tokens_partial": parent_tokens,
                    "explore_child_model_tokens": child_tokens,
                    "complete": False,
                    "source": "partial opencode event stream + available child session exports",
                },
                latency_seconds=time.monotonic() - started,
                valid=False,
                error=f"OpenCode timed out after {self.timeout_seconds}s",
                diagnostics={
                    "partial_event_count": len(events),
                    "explore_child_session_ids": child_ids,
                    "token_errors": token_errors,
                },
            )
        except OSError as exc:
            return RetrievalResult(
                self.name,
                case["case_id"],
                query_id,
                query,
                repeat,
                latency_seconds=time.monotonic() - started,
                valid=False,
                error=str(exc),
            )

        _, child_ids, parent_tokens, final_texts = self._parse_events(completed.stdout)
        evidence_ids, parse_error = self._parse_final_ids(final_texts)
        child_tokens = 0
        token_errors: list[str] = []
        for child_id in child_ids:
            value, error = self._export_session_tokens(child_id, execution_dir)
            if value is not None:
                child_tokens += value
            if error:
                token_errors.append(error)

        errors: list[str] = []
        if completed.returncode != 0:
            errors.append(completed.stderr.strip() or f"OpenCode exited {completed.returncode}")
        if len(child_ids) != 1:
            errors.append(f"expected exactly one explore child session, found {len(child_ids)}")
        if parse_error:
            errors.append(parse_error)

        token_complete = bool(child_ids) and not token_errors
        query_tokens = parent_tokens + child_tokens if parent_tokens or child_tokens else None
        return RetrievalResult(
            system=self.name,
            case_id=case["case_id"],
            query_id=query_id,
            query=query,
            repeat=repeat,
            evidence_ids=evidence_ids,
            query_tokens=query_tokens,
            token_details={
                "parent_model_tokens": parent_tokens,
                "explore_child_model_tokens": child_tokens,
                "complete": token_complete,
                "source": "opencode event stream + child session export",
            },
            latency_seconds=time.monotonic() - started,
            valid=not errors,
            error="; ".join(errors) if errors else None,
            diagnostics={
                "explore_child_session_ids": child_ids,
                "returncode": completed.returncode,
                "token_errors": token_errors,
            },
        )
