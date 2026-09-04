from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
from urllib.parse import urlparse


SUPPORTED_PROVIDERS = {"openai-compatible"}


@dataclass(frozen=True)
class LLMInferenceConfig:
    enabled: bool
    provider: str
    base_url: str
    model: str
    api_key_env: str | None = None
    timeout_seconds: float = 60.0
    max_retries: int = 2
    max_output_tokens: int = 2000
    temperature: float = 0.0
    max_sources: int = 50
    candidate_limit_per_type: int = 12
    max_input_characters: int = 60000
    minimum_confidence: float = 0.5
    prompt_version: str = "scenario-model-candidate-v1"

    @classmethod
    def from_mapping(cls, value: dict) -> "LLMInferenceConfig":
        if not isinstance(value, dict):
            raise ValueError("LLM inference config must be a JSON object")
        if "api_key" in value:
            raise ValueError("store only api_key_env in config; never store the API key")
        config = cls(
            enabled=bool(value.get("enabled", False)),
            provider=str(value.get("provider", "openai-compatible")),
            base_url=str(value.get("base_url", "")).rstrip("/"),
            model=str(value.get("model", "")).strip(),
            api_key_env=(str(value["api_key_env"]).strip() if value.get("api_key_env") else None),
            timeout_seconds=float(value.get("timeout_seconds", 60.0)),
            max_retries=int(value.get("max_retries", 2)),
            max_output_tokens=int(value.get("max_output_tokens", 2000)),
            temperature=float(value.get("temperature", 0.0)),
            max_sources=int(value.get("max_sources", 50)),
            candidate_limit_per_type=int(value.get("candidate_limit_per_type", 12)),
            max_input_characters=int(value.get("max_input_characters", 60000)),
            minimum_confidence=float(value.get("minimum_confidence", 0.5)),
            prompt_version=str(value.get("prompt_version", "scenario-model-candidate-v1")).strip(),
        )
        config.validate()
        return config

    def validate(self) -> None:
        if self.provider not in SUPPORTED_PROVIDERS:
            raise ValueError(f"unsupported LLM provider: {self.provider}")
        if self.api_key_env and not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", self.api_key_env):
            raise ValueError(
                "api_key_env must be an environment variable name, not a secret value"
            )
        parsed = urlparse(self.base_url)
        if not self.base_url or parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("base_url must be an absolute http(s) URL")
        if not self.model:
            raise ValueError("model is required")
        if not self.prompt_version:
            raise ValueError("prompt_version is required")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if not 0 <= self.max_retries <= 10:
            raise ValueError("max_retries must be between 0 and 10")
        if self.max_output_tokens < 128:
            raise ValueError("max_output_tokens must be at least 128")
        if not 0.0 <= self.temperature <= 1.0:
            raise ValueError("temperature must be between 0 and 1")
        if self.max_sources < 1:
            raise ValueError("max_sources must be positive")
        if not 1 <= self.candidate_limit_per_type <= 50:
            raise ValueError("candidate_limit_per_type must be between 1 and 50")
        if self.max_input_characters < 4000:
            raise ValueError("max_input_characters must be at least 4000")
        if not 0.0 <= self.minimum_confidence <= 1.0:
            raise ValueError("minimum_confidence must be between 0 and 1")

    def api_key(self, environ=None) -> str | None:
        if not self.api_key_env:
            return None
        value = (environ or os.environ).get(self.api_key_env)
        if self.enabled and not value:
            raise ValueError(f"LLM API key environment variable is not set: {self.api_key_env}")
        return value

    def public_metadata(self) -> dict:
        return {
            "provider": self.provider,
            "base_url": self.base_url,
            "model": self.model,
            "api_key_env": self.api_key_env,
            "timeout_seconds": self.timeout_seconds,
            "max_retries": self.max_retries,
            "max_output_tokens": self.max_output_tokens,
            "temperature": self.temperature,
            "max_sources": self.max_sources,
            "candidate_limit_per_type": self.candidate_limit_per_type,
            "max_input_characters": self.max_input_characters,
            "minimum_confidence": self.minimum_confidence,
            "prompt_version": self.prompt_version,
        }


def load_llm_inference_config(path) -> LLMInferenceConfig:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return LLMInferenceConfig.from_mapping(payload)
