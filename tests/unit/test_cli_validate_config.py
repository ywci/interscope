# tests/unit/test_cli_validate_config.py
#
# Unit tests for the `isir validate-config` CLI subcommand and the
# `validate_config` helper.

import copy
import pytest
import yaml
from pathlib import Path
from isir.cli.validate_config import validate_config, _setup_arg_parser


def _write_config(tmp_path, data) -> Path:
    """Write a YAML config dict to tmp_path and return its path."""
    p = tmp_path / "config.yaml"
    p.write_text(yaml.dump(data), encoding="utf-8")
    return p


_PERF_BASE = {
    "proof": {"perf": {"enabled": True}},
    "provers": {"koika": {"use_proof_library": False}},
}


class TestArgumentParser:
    def test_defaults(self):
        parser = _setup_arg_parser()
        args = parser.parse_args([])
        assert args.config is None
        assert args.debug is False

    def test_config_and_debug_flags(self):
        parser = _setup_arg_parser()
        args = parser.parse_args(["--config", "conf/config.yaml", "--debug"])
        assert args.config == "conf/config.yaml"
        assert args.debug is True

    def test_short_config_flag(self):
        parser = _setup_arg_parser()
        args = parser.parse_args(["-c", "custom.yaml"])
        assert args.config == "custom.yaml"


class TestValidateConfig:
    def test_valid_config_returns_true(self, tmp_path):
        cfg = {
            "proof": {"perf": {"enabled": False}},
            "provers": {"koika": {"use_proof_library": True}},
        }
        assert validate_config(_write_config(tmp_path, cfg), verbose=False) is True

    def test_perf_use_proof_library_conflict_returns_false(self, tmp_path):
        cfg = {
            "proof": {"perf": {"enabled": True}},
            "provers": {"koika": {"use_proof_library": True}},
        }
        assert validate_config(_write_config(tmp_path, cfg), verbose=False) is False

    def test_perf_with_library_disabled_returns_true(self, tmp_path):
        cfg = {
            "proof": {"perf": {"enabled": True}},
            "provers": {"koika": {"use_proof_library": False}},
        }
        assert validate_config(_write_config(tmp_path, cfg), verbose=False) is True

    def test_provider_needing_key_without_key_returns_true(self, tmp_path, monkeypatch):
        """A keyed provider with no key/env is only a warning, not an error."""
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        cfg = copy.deepcopy(_PERF_BASE)
        cfg["llm"] = {"provider": "deepseek", "model": "qwen3.5:27b"}
        assert validate_config(_write_config(tmp_path, cfg), verbose=False) is True

    def test_provider_with_env_key_emits_no_missing_key_warning(
        self, tmp_path, monkeypatch, capsys
    ):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test-key")
        cfg = copy.deepcopy(_PERF_BASE)
        cfg["llm"] = {"provider": "deepseek", "model": "qwen3.5:27b"}
        assert validate_config(_write_config(tmp_path, cfg), verbose=True) is True
        out = capsys.readouterr().out
        assert "requires an API key" not in out

    def test_provider_without_key_emits_warning(self, tmp_path, monkeypatch, capsys):
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        cfg = copy.deepcopy(_PERF_BASE)
        cfg["llm"] = {"provider": "deepseek", "model": "qwen3.5:27b"}
        assert validate_config(_write_config(tmp_path, cfg), verbose=True) is True
        out = capsys.readouterr().out
        assert "requires an API key" in out
        assert "DEEPSEEK_API_KEY" in out
        assert "No errors found" in out

    def test_missing_file_returns_false(self, tmp_path):
        assert validate_config(tmp_path / "nope.yaml", verbose=False) is False

    def test_yaml_parse_error_returns_false(self, tmp_path):
        p = tmp_path / "config.yaml"
        p.write_text("key: [unclosed", encoding="utf-8")
        assert validate_config(p, verbose=False) is False

    def test_non_dict_root_returns_false(self, tmp_path):
        p = tmp_path / "config.yaml"
        p.write_text("- item1\n- item2\n", encoding="utf-8")
        assert validate_config(p, verbose=False) is False

    def test_invalid_perf_numeric_field_returns_false(self, tmp_path):
        cfg = copy.deepcopy(_PERF_BASE)
        cfg["proof"]["perf"].update(
            {"beam_size": 0, "branches_per_node": 1, "depth_limit": 1, "dimensions": ["a"]}
        )
        cfg["llm"] = {"provider": "ollama", "model": "qwen"}
        assert validate_config(_write_config(tmp_path, cfg), verbose=False) is False

    def test_unsupported_provider_emits_warning(self, tmp_path, capsys):
        cfg = copy.deepcopy(_PERF_BASE)
        cfg["llm"] = {"provider": "madeup", "model": "some-model"}
        assert validate_config(_write_config(tmp_path, cfg), verbose=True) is True
        out = capsys.readouterr().out
        assert "Unsupported LLM provider 'madeup'" in out

    def test_empty_dimensions_emits_warning(self, tmp_path, capsys):
        cfg = copy.deepcopy(_PERF_BASE)
        cfg["llm"] = {"provider": "ollama", "model": "qwen"}
        cfg["proof"]["perf"]["dimensions"] = []
        assert validate_config(_write_config(tmp_path, cfg), verbose=True) is True
        out = capsys.readouterr().out
        assert "'dimensions' list is empty" in out
