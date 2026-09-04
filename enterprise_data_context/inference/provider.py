from __future__ import annotations

import json
import time
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .config import LLMInferenceConfig


class StructuredInferenceProvider(Protocol):
    def infer(self, *, system_prompt: str, payload: dict) -> dict: ...


class LLMProviderError(RuntimeError):
    pass


class OpenAICompatibleProvider:
    """Dependency-free client for an OpenAI-compatible chat-completions endpoint."""

    def __init__(self, config: LLMInferenceConfig, *, opener=urlopen, sleeper=time.sleep):
        config.validate()
        if not config.enabled:
            raise ValueError("LLM inference is disabled in config")
        self.config = config
        self.api_key = config.api_key()
        self.opener = opener
        self.sleeper = sleeper

    def infer(self, *, system_prompt: str, payload: dict) -> dict:
        body = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_output_tokens,
            "response_format": {"type": "json_object"},
        }
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        endpoint = f"{self.config.base_url}/chat/completions"

        for attempt in range(self.config.max_retries + 1):
            request = Request(
                endpoint,
                data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                headers=headers,
                method="POST",
            )
            try:
                with self.opener(request, timeout=self.config.timeout_seconds) as response:
                    result = json.loads(response.read().decode("utf-8"))
                content = result["choices"][0]["message"]["content"]
                if isinstance(content, list):
                    content = "".join(
                        item.get("text", "") for item in content if isinstance(item, dict)
                    )
                parsed = json.loads(content)
                if not isinstance(parsed, dict):
                    raise LLMProviderError("LLM structured response must be a JSON object")
                return parsed
            except HTTPError as exc:
                retryable = exc.code == 429 or 500 <= exc.code < 600
                if not retryable or attempt >= self.config.max_retries:
                    raise LLMProviderError(f"LLM request failed with HTTP {exc.code}") from exc
            except (URLError, TimeoutError) as exc:
                if attempt >= self.config.max_retries:
                    raise LLMProviderError(f"LLM request failed: {type(exc).__name__}") from exc
            except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
                raise LLMProviderError("LLM response is not a valid structured completion") from exc
            self.sleeper(min(2 ** attempt, 4))
        raise LLMProviderError("LLM request exhausted retries")


def provider_from_config(config: LLMInferenceConfig) -> StructuredInferenceProvider:
    if config.provider == "openai-compatible":
        return OpenAICompatibleProvider(config)
    raise ValueError(f"unsupported LLM provider: {config.provider}")
