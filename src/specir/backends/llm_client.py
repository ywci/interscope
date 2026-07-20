# src/specir/backends/llm_client.py
#
# Low-level LLM client supporting OpenAI, Anthropic, local (Ollama), and DeepSeek.
# Provides a uniform interface for proof generation and hint repair.
# Enhanced with debug logging for prompts and responses to track proof progress.

import os
import time
import logging
from typing import Any, Dict, List, Optional, Union

from specir.utils.logger import get_logger

logger = get_logger(__name__)

try:
    from openai import OpenAI
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False

try:
    import anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


class LLMClientError(Exception):
    """Raised when LLM API calls fail after all retries."""
    pass


class LLMClient:
    """Generic LLM client with support for multiple providers."""
    def __init__(
        self,
        provider: str,
        model: str,
        api_key: Optional[str] = None,
        api_base: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 2048,
        timeout: int = 120,
        retries: int = 3
    ):
        self.provider = provider.lower()
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout
        self.retries = retries

        if self.provider == "deepseek":
            self.provider = "openai"
            if api_base is None:
                api_base = "https://api.deepseek.com/v1"
            if api_key is None:
                api_key = os.environ.get("DEEPSEEK_API_KEY")

        if api_key is None:
            env_var = f"{self.provider.upper()}_API_KEY"
            api_key = os.environ.get(env_var)

        self.api_key = api_key
        self.api_base = api_base
        self._client = None

        if self.provider in ("openai", "ollama", "local"):
            if not HAS_OPENAI:
                raise ImportError(
                    "OpenAI client library required. Install with: pip install openai"
                )
            client_kwargs: Dict[str, Any] = {
                "api_key": self.api_key or "not-needed",
                "timeout": self.timeout
            }
            if self.api_base:
                client_kwargs["base_url"] = self.api_base
            self._client = OpenAI(**client_kwargs)

        elif self.provider == "anthropic":
            if not HAS_ANTHROPIC:
                raise ImportError(
                    "Anthropic client library required. Install with: pip install anthropic"
                )
            if not self.api_key:
                raise ValueError(
                    "Anthropic API key is required. "
                    "Set ANTHROPIC_API_KEY environment variable."
                )
            self._client = anthropic.Anthropic(api_key=self.api_key)

        else:
            raise ValueError(f"Unsupported provider: {self.provider}")

        self._total_prompt_tokens = 0
        self._total_completion_tokens = 0

    def generate(
        self,
        prompt: Optional[str] = None,
        messages: Optional[List[Dict[str, str]]] = None,
        system: Optional[str] = None
    ) -> str:
        """
        Generate a completion.

        Accepts either a simple prompt string or a full chat‑message list.
        If both are provided, *messages* takes precedence.

        Args:
            prompt: User message string (for simple single‑turn).
            messages: Full chat message list (list of dicts with "role" and "content").
            system: Optional system prompt (prepended to messages if provided).
        """
        if messages is None:
            if prompt is None:
                raise ValueError("Either prompt or messages must be provided")
            messages = [{"role": "user", "content": prompt}]
        if system:
            messages = [{"role": "system", "content": system}] + messages

        if logger.isEnabledFor(logging.DEBUG):
            compact = []
            for m in messages:
                role = m.get("role", "?")
                content = m.get("content", "")
                if len(content) > 200:
                    content = content[:200] + "..."
                compact.append(f"[{role}] {content}")
            logger.debug("LLM prompt to %s (%s): %s", self.provider, self.model, "\n".join(compact))

        if self.provider in ("openai", "ollama", "local"):
            result = self._call_openai(messages)
        elif self.provider == "anthropic":
            result = self._call_anthropic(messages)
        else:
            raise ValueError(f"Unsupported provider: {self.provider}")

        logger.debug("LLM response (%d chars): %s", len(result), result[:500])
        return result

    @property
    def total_tokens_used(self) -> Dict[str, int]:
        """Return cumulative token usage (prompt + completion)."""
        return {
            "prompt_tokens": self._total_prompt_tokens,
            "completion_tokens": self._total_completion_tokens
        }

    def _call_openai(self, messages: List[Dict[str, str]]) -> str:
        """Use the OpenAI (or compatible) chat completions endpoint."""
        for attempt in range(self.retries):
            try:
                response = self._client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=self.temperature,
                    max_tokens=self.max_tokens
                )

                if hasattr(response, "usage") and response.usage:
                    self._total_prompt_tokens += response.usage.prompt_tokens
                    self._total_completion_tokens += response.usage.completion_tokens
                return response.choices[0].message.content
            except Exception as e:
                if not self._should_retry(attempt, "OpenAI", e):
                    raise LLMClientError(f"OpenAI API call failed: {e}") from e

    def _call_anthropic(self, messages: List[Dict[str, str]]) -> str:
        """Use the Anthropic Messages API."""
        system_content = None
        user_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system_content = msg["content"]
            else:
                user_messages.append(msg)

        for attempt in range(self.retries):
            try:
                response = self._client.messages.create(
                    model=self.model,
                    max_tokens=self.max_tokens,
                    temperature=self.temperature,
                    system=system_content,
                    messages=user_messages
                )
                if hasattr(response, "usage"):
                    self._total_prompt_tokens += response.usage.input_tokens
                    self._total_completion_tokens += response.usage.output_tokens
                return response.content[0].text
            except Exception as e:
                if not self._should_retry(attempt, "Anthropic", e):
                    raise LLMClientError(f"Anthropic API call failed: {e}") from e

    def _should_retry(self, attempt: int, provider_name: str, error: Exception) -> bool:
        """Return True if we should retry, False to raise."""
        if attempt < self.retries - 1:
            delay = 2 ** attempt
            logger.warning(
                "%s attempt %d/%d failed: %s. Retrying in %ds...",
                provider_name, attempt + 1, self.retries, error, delay,
            )
            time.sleep(delay)
            return True
        return False


def get_llm_client_from_config(config: Dict[str, Any]) -> LLMClient:
    """Create an LLMClient from the global configuration dictionary."""
    llm_cfg = config.get("llm", {})
    return LLMClient(
        provider=llm_cfg.get("provider", "openai"),
        model=llm_cfg.get("model", "gpt-4"),
        api_key=llm_cfg.get("api_key"),
        api_base=llm_cfg.get("base_url") or llm_cfg.get("api_base"),
        temperature=llm_cfg.get("temperature", 0.2),
        max_tokens=llm_cfg.get("max_tokens", 2048),
        timeout=llm_cfg.get("timeout", 120),
        retries=llm_cfg.get("retries", 3)
    )
