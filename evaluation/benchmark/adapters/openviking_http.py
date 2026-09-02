from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from .base import RetrievalAdapter, extract_evidence_ids
from ..models import RetrievalResult
from ..tokens import estimate_tokens, extract_telemetry_tokens, recursive_strings


class OpenVikingHTTPAdapter(RetrievalAdapter):
    name = "openviking"

    def __init__(self, config: dict[str, Any], corpus_dir: Path):
        super().__init__(config, corpus_dir)
        self.base_url = str(config.get("base_url", "http://127.0.0.1:1933")).rstrip("/")
        self.api_key_env = str(config.get("api_key_env", "OPENVIKING_API_KEY"))
        self.account_env = config.get("account_env")
        self.user_env = config.get("user_env")
        self.actor_peer_env = config.get("actor_peer_env")
        self.mode = str(config.get("mode", "search"))
        self.target_uri = str(config.get("target_uri", "viking://resources/data-context-eval"))
        self.limit = int(config.get("limit", 20))
        self.timeout_seconds = int(config.get("timeout_seconds", 90))
        self.read_content = bool(config.get("read_content", True))
        if self.mode not in {"find", "search"}:
            raise ValueError("OpenViking mode must be 'find' or 'search'")

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        api_key = os.environ.get(self.api_key_env)
        if api_key:
            headers["X-API-Key"] = api_key
        if self.account_env and os.environ.get(str(self.account_env)):
            headers["X-OpenViking-Account"] = os.environ[str(self.account_env)]
        if self.user_env and os.environ.get(str(self.user_env)):
            headers["X-OpenViking-User"] = os.environ[str(self.user_env)]
        if self.actor_peer_env and os.environ.get(str(self.actor_peer_env)):
            headers["X-OpenViking-Actor-Peer"] = os.environ[str(self.actor_peer_env)]
        return headers

    def _request(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = urllib.request.Request(
            self.base_url + path,
            data=data,
            headers=self._headers(),
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:1000]
            raise RuntimeError(f"OpenViking HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"OpenViking connection failed: {exc.reason}") from exc

    @staticmethod
    def _unwrap(payload: Any) -> Any:
        if isinstance(payload, dict) and payload.get("status") == "ok" and "result" in payload:
            return payload["result"]
        return payload

    @staticmethod
    def _hits(result: Any) -> list[dict[str, Any]]:
        if isinstance(result, list):
            return [item for item in result if isinstance(item, dict)]
        if not isinstance(result, dict):
            return []
        hits: list[dict[str, Any]] = []
        for key in ("resources", "memories", "skills", "contexts", "matches"):
            value = result.get(key, [])
            if isinstance(value, list):
                hits.extend(item for item in value if isinstance(item, dict))
        return hits

    @staticmethod
    def _budgeted_context(hits: list[dict[str, Any]], token_budget: int) -> tuple[str, int, bool]:
        selected: list[str] = []
        used = 0
        truncated = False
        for hit in hits:
            text = "\n".join(recursive_strings(hit))
            hit_tokens = estimate_tokens(text)
            if used + hit_tokens <= token_budget:
                selected.append(text)
                used += hit_tokens
                continue
            remaining = token_budget - used
            if remaining > 0:
                low, high = 0, len(text)
                while low < high:
                    middle = (low + high + 1) // 2
                    if estimate_tokens(text[:middle]) <= remaining:
                        low = middle
                    else:
                        high = middle - 1
                if low:
                    selected.append(text[:low])
                    used += estimate_tokens(text[:low])
            truncated = True
            break
        return "\n".join(selected), used, truncated

    def preflight(self) -> dict[str, Any]:
        payload = self._request("GET", "/health")
        status = payload.get("status") if isinstance(payload, dict) else None
        if status != "ok":
            raise RuntimeError(f"OpenViking health check was not ok: {payload}")
        return {
            "base_url": self.base_url,
            "mode": self.mode,
            "target_uri": self.target_uri,
            "limit": self.limit,
            "read_content": self.read_content,
            "api_key_present": bool(os.environ.get(self.api_key_env)),
        }

    def retrieve(
        self,
        case: dict[str, Any],
        query: str,
        query_id: str,
        repeat: int,
    ) -> RetrievalResult:
        started = time.monotonic()
        body: dict[str, Any] = {
            "query": query,
            "target_uri": self.target_uri,
            "context_type": "resource",
            "limit": self.limit,
            "include_provenance": True,
            "read_content": self.read_content,
            "telemetry": True,
        }
        try:
            payload = self._request("POST", f"/api/v1/search/{self.mode}", body)
            result = self._unwrap(payload)
            hits = self._hits(result)
            context_text, context_tokens, truncated = self._budgeted_context(
                hits, int(case["context_token_budget"])
            )
            evidence_ids = extract_evidence_ids(context_text)
            model_tokens = extract_telemetry_tokens(payload)
            return RetrievalResult(
                system=self.name,
                case_id=case["case_id"],
                query_id=query_id,
                query=query,
                repeat=repeat,
                evidence_ids=evidence_ids,
                query_tokens=(model_tokens or 0) + context_tokens,
                token_details={
                    "native_model_tokens": model_tokens,
                    "retrieved_context_tokens_estimated": context_tokens,
                    "complete": model_tokens is not None,
                    "source": "OpenViking operation telemetry + deterministic context estimate",
                },
                latency_seconds=time.monotonic() - started,
                diagnostics={
                    "hit_count": len(hits),
                    "mode": self.mode,
                    "context_budget": int(case["context_token_budget"]),
                    "context_truncated": truncated,
                },
            )
        except Exception as exc:  # Adapter boundary: preserve typed failure in result.
            return RetrievalResult(
                system=self.name,
                case_id=case["case_id"],
                query_id=query_id,
                query=query,
                repeat=repeat,
                latency_seconds=time.monotonic() - started,
                valid=False,
                error=str(exc),
                diagnostics={"mode": self.mode},
            )
