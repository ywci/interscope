# src/specir/backends/llm_client.py
#
# Low‑level LLM client supporting OpenAI, Anthropic, Ollama, and DeepSeek.

import os
import time
import json
import logging
import concurrent.futures
import threading
from typing import Any, Dict, List, Optional, Union, Callable
from specir.utils.logger import get_logger

logger = get_logger(__name__)

try:
    from openai import OpenAI
    import httpx
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
    """Generic LLM client with support for multiple providers.

    PERF extensions:
        generate_batch():   Execute multiple prompts in parallel using threads.
        generate_structured(): Request JSON-structured output (OpenAI-only, fallback to parsing).
    """

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

        # DeepSeek is OpenAI‑compatible
        if self.provider == "deepseek":
            self.provider = "openai"
            if api_base is None:
                api_base = "https://api.deepseek.com/v1"
            if api_key is None:
                api_key = os.environ.get("DEEPSEEK_API_KEY")

        # Obtain API key from environment if not provided
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
            # Use a httpx.Timeout object with distinct connect/read/write/pool timeouts
            client_timeout = httpx.Timeout(
                connect=10.0,
                read=self.timeout,
                write=10.0,
                pool=10.0
            )
            client_kwargs: Dict[str, Any] = {
                "api_key": self.api_key or "not-needed",
                "timeout": client_timeout,
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
            self._client = anthropic.Anthropic(
                api_key=self.api_key,
                timeout=self.timeout,
            )

        else:
            raise ValueError(f"Unsupported provider: {self.provider}")

        self._total_prompt_tokens = 0
        self._total_completion_tokens = 0

    def _call_with_timeout(self, func, timeout: float, *args, **kwargs) -> Any:
        """
        Execute *func* in a daemon thread and abort if it exceeds *timeout* seconds.
        Returns the return value of *func* on success, raises LLMClientError on timeout.
        """
        result_container = {}
        exception_container = []

        def target():
            try:
                result_container["value"] = func(*args, **kwargs)
            except Exception as e:
                exception_container.append(e)

        thread = threading.Thread(target=target, daemon=True)
        thread.start()
        thread.join(timeout=timeout)

        if thread.is_alive():
            raise LLMClientError(f"LLM call timed out after {timeout}s")

        if exception_container:
            raise exception_container[0]

        return result_container.get("value")

    def generate(
        self,
        prompt: Optional[str] = None,
        messages: Optional[List[Dict[str, str]]] = None,
        system: Optional[str] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        """
        Generate a completion.

        Accepts either a simple prompt string or a full chat‑message list.
        If both are provided, *messages* takes precedence.

        Args:
            prompt: User message string (for simple single‑turn).
            messages: Full chat message list (list of dicts with "role" and "content").
            system: Optional system prompt (prepended to messages if provided).
            max_tokens: Override the default max_tokens for this call.

        Returns:
            The generated text.
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
            result = self._call_openai(messages, max_tokens)
        elif self.provider == "anthropic":
            result = self._call_anthropic(messages, max_tokens)
        else:
            raise ValueError(f"Unsupported provider: {self.provider}")

        logger.debug("LLM response (%d chars): %s", len(result), result[:500])
        return result

    def _call_openai(self, messages: List[Dict[str, str]], max_tokens: Optional[int] = None) -> str:
        """Use the OpenAI (or compatible) chat completions endpoint."""
        effective_timeout = self.timeout + 30   # give a little extra over the HTTP timeout
        for attempt in range(self.retries):
            try:
                # Wrap the actual API call in a thread to enforce a hard deadline
                return self._call_with_timeout(
                    self._openai_request, effective_timeout, messages, max_tokens
                )
            except LLMClientError as e:
                # Explicit timeout – no retry, re‑raise
                raise
            except Exception as e:
                if not self._should_retry(attempt, "OpenAI", e):
                    raise LLMClientError(f"OpenAI API call failed: {e}") from e

    def _openai_request(self, messages: List[Dict[str, str]], max_tokens: Optional[int]) -> str:
        """The actual OpenAI API call – may be called in a thread."""
        response = self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
            max_tokens=max_tokens or self.max_tokens,
        )
        if hasattr(response, "usage") and response.usage:
            self._total_prompt_tokens += response.usage.prompt_tokens
            self._total_completion_tokens += response.usage.completion_tokens
        return response.choices[0].message.content

    def _call_anthropic(self, messages: List[Dict[str, str]], max_tokens: Optional[int] = None) -> str:
        """Use the Anthropic Messages API."""
        system_content = None
        user_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system_content = msg["content"]
            else:
                user_messages.append(msg)

        effective_timeout = self.timeout + 30
        for attempt in range(self.retries):
            try:
                return self._call_with_timeout(
                    self._anthropic_request, effective_timeout,
                    system_content, user_messages, max_tokens
                )
            except LLMClientError:
                raise
            except Exception as e:
                if not self._should_retry(attempt, "Anthropic", e):
                    raise LLMClientError(f"Anthropic API call failed: {e}") from e

    def _anthropic_request(self, system_content: Optional[str],
                           user_messages: List[Dict[str, str]],
                           max_tokens: Optional[int]) -> str:
        """The actual Anthropic API call."""
        response = self._client.messages.create(
            model=self.model,
            max_tokens=max_tokens or self.max_tokens,
            temperature=self.temperature,
            system=system_content,
            messages=user_messages,
        )
        if hasattr(response, "usage"):
            self._total_prompt_tokens += response.usage.input_tokens
            self._total_completion_tokens += response.usage.output_tokens
        return response.content[0].text

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

    def generate_batch(
        self,
        prompts: List[str],
        system: Optional[str] = None,
        max_workers: int = 4,
        max_tokens: Optional[int] = None,
    ) -> List[str]:
        """
        Generate completions for multiple prompts in parallel.

        This is used by PERF to generate multiple divergent proof attempts
        concurrently, reducing latency.

        Args:
            prompts: List of prompt strings.
            system: Optional system prompt (applied to all).
            max_workers: Maximum number of concurrent threads.
            max_tokens: Override max_tokens for each call.

        Returns:
            List of responses in the same order as prompts.
        """
        if not prompts:
            return []

        if len(prompts) == 1:
            return [self.generate(prompt=prompts[0], system=system, max_tokens=max_tokens)]

        def _generate_single(prompt: str) -> str:
            return self.generate(prompt=prompt, system=system, max_tokens=max_tokens)

        results = [None] * len(prompts)
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_idx = {
                executor.submit(_generate_single, prompt): idx
                for idx, prompt in enumerate(prompts)
            }
            for future in concurrent.futures.as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    results[idx] = future.result()
                except Exception as e:
                    logger.error("Batch generation for prompt %d failed: %s", idx, e)
                    results[idx] = ""

        return results

    def generate_structured(
        self,
        prompt: str,
        response_format: Dict[str, Any],
        system: Optional[str] = None,
        max_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Generate a structured (JSON) response for reflection scoring.

        This is used by PERF's Pareto scorer to get dimension preferences
        in a machine-readable format.

        Args:
            prompt: The prompt to send.
            response_format: A JSON Schema dict (for OpenAI) or a description of
                             expected fields (used for fallback parsing).
            system: Optional system prompt.
            max_tokens: Override max_tokens.

        Returns:
            A dictionary with the parsed JSON response.

        Raises:
            LLMClientError: If the response cannot be parsed as JSON.
        """
        # For OpenAI-compatible APIs, use the response_format parameter if available.
        if self.provider in ("openai", "ollama", "local"):
            try:
                response = self._client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=self.temperature,
                    max_tokens=max_tokens or self.max_tokens,
                    response_format=response_format,
                )
                content = response.choices[0].message.content
                try:
                    return json.loads(content)
                except json.JSONDecodeError:
                    cleaned = content.strip()
                    if cleaned.startswith("```json"):
                        cleaned = cleaned[7:]
                    if cleaned.endswith("```"):
                        cleaned = cleaned[:-3]
                    try:
                        return json.loads(cleaned.strip())
                    except json.JSONDecodeError as e:
                        raise LLMClientError(f"Failed to parse structured response: {e}\nResponse: {content}")
            except AttributeError:
                logger.debug("response_format not supported by provider; falling back to free generation and parsing.")
                content = self.generate(prompt=prompt, system=system, max_tokens=max_tokens)
                return self._parse_structured_response(content, response_format)

        # For Anthropic and other providers, generate free text and parse.
        content = self.generate(prompt=prompt, system=system, max_tokens=max_tokens)
        return self._parse_structured_response(content, response_format)

    def _parse_structured_response(self, content: str, response_format: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse a free-text response into a structured dict.
        Tries to extract JSON from the content.
        """
        cleaned = content.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

        try:
            if cleaned.startswith("{") and cleaned.endswith("}"):
                return json.loads(cleaned)
            else:
                import re
                match = re.search(r'\{.*\}', cleaned, re.DOTALL)
                if match:
                    return json.loads(match.group(0))
                else:
                    raise json.JSONDecodeError("No JSON object found", cleaned, 0)
        except json.JSONDecodeError as e:
            raise LLMClientError(
                f"Failed to parse structured response: {e}\nContent: {content[:500]}"
            )

    @property
    def total_tokens_used(self) -> Dict[str, int]:
        """Return cumulative token usage (prompt + completion)."""
        return {
            "prompt_tokens": self._total_prompt_tokens,
            "completion_tokens": self._total_completion_tokens
        }


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
