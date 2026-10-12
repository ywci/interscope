# tests/unit/test_llm_client.py
#
# Unit tests for LLM provider API-key resolution, including automatic
# selection of the provider-specific environment variable.

from unittest.mock import Mock
from isir.backends import llm_client
from isir.backends.llm_client import (
    PROVIDER_API_KEY_ENV,
    PROVIDER_API_BASE_ENV,
    PROVIDER_API_BASE_DEFAULTS,
    resolve_api_key,
    resolve_api_base,
    LLMClient,
)


class TestResolveApiKey:
    def test_explicit_key_wins(self):
        assert resolve_api_key("openai", "sk-explicit") == "sk-explicit"

    def test_placeholder_falls_back_to_env(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-env")
        assert resolve_api_key("openai", "not-needed") == "sk-env"
        assert resolve_api_key("openai", "") == "sk-env"
        assert resolve_api_key("openai", "changeme") == "sk-env"

    def test_deepseek_env_var(self, monkeypatch):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-deepseek")
        assert resolve_api_key("deepseek", "") == "sk-deepseek"

    def test_provider_env_mapping(self):
        assert PROVIDER_API_KEY_ENV["openai"] == "OPENAI_API_KEY"
        assert PROVIDER_API_KEY_ENV["anthropic"] == "ANTHROPIC_API_KEY"
        assert PROVIDER_API_KEY_ENV["deepseek"] == "DEEPSEEK_API_KEY"
        assert PROVIDER_API_KEY_ENV["ollama"] == "OLLAMA_API_KEY"

    def test_missing_key_returns_none(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        assert resolve_api_key("openai", None) is None
        assert resolve_api_key("openai", "not-needed") is None

    def test_ollama_no_key_is_ok(self, monkeypatch):
        monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
        assert resolve_api_key("ollama", "not-needed") is None

    def test_unknown_provider_with_explicit_key(self):
        assert resolve_api_key("unknown", "sk-key") == "sk-key"

    def test_key_is_stripped(self):
        assert resolve_api_key("openai", "  sk-key  ") == "sk-key"


class TestLLMClientKeyResolution:
    def test_constructor_resolves_deepseek_env_key(self, monkeypatch):
        monkeypatch.setattr(llm_client, "HAS_OPENAI", True)
        monkeypatch.setattr(llm_client, "OpenAI", Mock())
        monkeypatch.setattr(llm_client, "httpx", Mock())
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-deepseek")
        monkeypatch.delenv("DEEPSEEK_API_BASE", raising=False)
        monkeypatch.delenv("DEEPSEEK_BASE_URL", raising=False)
        client = LLMClient(provider="deepseek", model="deepseek-chat")
        assert client.api_key == "sk-deepseek"
        assert client.provider == "openai"
        assert client.api_base == "https://api.deepseek.com/v1"

    def test_constructor_placeholder_uses_env(self, monkeypatch):
        monkeypatch.setattr(llm_client, "HAS_OPENAI", True)
        monkeypatch.setattr(llm_client, "OpenAI", Mock())
        monkeypatch.setattr(llm_client, "httpx", Mock())
        monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")
        client = LLMClient(provider="openai", model="gpt-4", api_key="not-needed")
        assert client.api_key == "sk-openai"


class TestResolveApiBase:
    def test_explicit_base_wins(self):
        assert resolve_api_base("openai", "http://explicit/v1") == "http://explicit/v1"

    def test_provider_env_var(self, monkeypatch):
        monkeypatch.setenv("DEEPSEEK_API_BASE", "http://deepseek/v1")
        assert resolve_api_base("deepseek", "") == "http://deepseek/v1"

    def test_base_url_spelling_fallback(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_BASE", raising=False)
        monkeypatch.setenv("OPENAI_BASE_URL", "http://openai/v1")
        assert resolve_api_base("openai", None) == "http://openai/v1"

    def test_api_base_preferred_over_base_url(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_BASE", "http://first/v1")
        monkeypatch.setenv("OPENAI_BASE_URL", "http://second/v1")
        assert resolve_api_base("openai", None) == "http://first/v1"

    def test_missing_returns_none(self, monkeypatch):
        monkeypatch.delenv("DEEPSEEK_API_BASE", raising=False)
        monkeypatch.delenv("DEEPSEEK_BASE_URL", raising=False)
        assert resolve_api_base("deepseek", None) is None

    def test_mapping_and_defaults(self):
        assert PROVIDER_API_BASE_ENV["deepseek"] == ("DEEPSEEK_API_BASE", "DEEPSEEK_BASE_URL")
        assert PROVIDER_API_BASE_ENV["openai"] == ("OPENAI_API_BASE", "OPENAI_BASE_URL")
        assert PROVIDER_API_BASE_DEFAULTS["ollama"] == "http://localhost:11434/v1"
        assert PROVIDER_API_BASE_DEFAULTS["deepseek"] == "https://api.deepseek.com/v1"


class TestLLMClientBaseResolution:
    def _mock_openai_deps(self, monkeypatch):
        monkeypatch.setattr(llm_client, "HAS_OPENAI", True)
        monkeypatch.setattr(llm_client, "OpenAI", Mock())
        monkeypatch.setattr(llm_client, "httpx", Mock())

    def test_constructor_deepseek_default_base(self, monkeypatch):
        self._mock_openai_deps(monkeypatch)
        monkeypatch.delenv("DEEPSEEK_API_BASE", raising=False)
        monkeypatch.delenv("DEEPSEEK_BASE_URL", raising=False)
        client = LLMClient(provider="deepseek", model="deepseek-chat")
        assert client.api_base == "https://api.deepseek.com/v1"

    def test_constructor_deepseek_env_base(self, monkeypatch):
        self._mock_openai_deps(monkeypatch)
        monkeypatch.setenv("DEEPSEEK_API_BASE", "http://deepseek-proxy:8080/v1")
        client = LLMClient(provider="deepseek", model="deepseek-chat")
        assert client.api_base == "http://deepseek-proxy:8080/v1"
        assert llm_client.OpenAI.call_args.kwargs["base_url"] == "http://deepseek-proxy:8080/v1"

    def test_constructor_ollama_default_base(self, monkeypatch):
        self._mock_openai_deps(monkeypatch)
        monkeypatch.delenv("OLLAMA_API_BASE", raising=False)
        monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
        client = LLMClient(provider="ollama", model="llama3")
        assert client.api_base == "http://localhost:11434/v1"

    def test_constructor_openai_base_url_spelling(self, monkeypatch):
        self._mock_openai_deps(monkeypatch)
        monkeypatch.delenv("OPENAI_API_BASE", raising=False)
        monkeypatch.setenv("OPENAI_BASE_URL", "http://openai-proxy:9000/v1")
        client = LLMClient(provider="openai", model="gpt-4")
        assert client.api_base == "http://openai-proxy:9000/v1"

    def test_constructor_anthropic_env_base(self, monkeypatch):
        monkeypatch.setattr(llm_client, "HAS_ANTHROPIC", True)
        monkeypatch.setattr(llm_client, "anthropic", Mock())
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-anthropic")
        monkeypatch.setenv("ANTHROPIC_API_BASE", "http://anthropic-proxy:8080")
        client = LLMClient(provider="anthropic", model="claude-3")
        assert client.api_base == "http://anthropic-proxy:8080"
        assert llm_client.anthropic.Anthropic.call_args.kwargs["base_url"] == "http://anthropic-proxy:8080"
