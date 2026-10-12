# tests/unit/test_config_loader.py
#
# Unit tests for the configuration loader.
# Covers environment-variable substitution, deep merging, external config
# loading, PERF environment overrides, default injection, caching, and the
# singleton access helpers (get_config / reload_config).

import os
import pytest
import yaml
from pathlib import Path
from isir.utils import config_loader
from isir.utils.config_loader import (
    _apply_perf_env_overrides,
    _find_project_root,
    _substitute_env_vars,
    deep_merge_configs,
    get_config,
    load_config,
    load_external_config,
    reload_config,
)


def _write_yaml(path: Path, data) -> Path:
    """Write a YAML file (creating parent dirs) and return its path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


@pytest.fixture(autouse=True)
def _reset_config_state(monkeypatch):
    """Isolate module-level singletons and strip interfering env vars."""
    monkeypatch.setattr(config_loader, "_CONFIG", None)
    monkeypatch.setattr(config_loader, "_PROJECT_ROOT", None)
    for name in list(os.environ):
        if name.startswith("PERF_") or name == "SPECIR_CONFIG":
            monkeypatch.delenv(name, raising=False)
    yield


class TestSubstituteEnvVars:
    def test_simple_substitution(self, monkeypatch):
        monkeypatch.setenv("FOO", "bar")
        assert _substitute_env_vars("${FOO}") == "bar"

    def test_missing_var_kept_verbatim(self, monkeypatch):
        monkeypatch.delenv("TOTALLY_MISSING_VAR", raising=False)
        assert _substitute_env_vars("${TOTALLY_MISSING_VAR}") == "${TOTALLY_MISSING_VAR}"

    def test_multiple_vars_in_one_string(self, monkeypatch):
        monkeypatch.setenv("A", "1")
        monkeypatch.setenv("B", "2")
        assert _substitute_env_vars("${A}-${B}-${A}") == "1-2-1"

    def test_embedded_in_larger_string(self, monkeypatch):
        monkeypatch.setenv("NAME", "world")
        assert _substitute_env_vars("hello ${NAME}!") == "hello world!"

    def test_no_pattern_unchanged(self):
        assert _substitute_env_vars("plain text") == "plain text"

    def test_dict_recursion(self, monkeypatch):
        monkeypatch.setenv("K", "v")
        result = _substitute_env_vars({"a": "${K}", "b": {"c": "${K}"}})
        assert result == {"a": "v", "b": {"c": "v"}}

    def test_list_recursion(self, monkeypatch):
        monkeypatch.setenv("K", "v")
        result = _substitute_env_vars(["${K}", ["${K}", 1]])
        assert result == ["v", ["v", 1]]

    def test_non_string_values_pass_through(self, monkeypatch):
        monkeypatch.setenv("K", "v")
        assert _substitute_env_vars(42) == 42
        assert _substitute_env_vars(True) is True
        assert _substitute_env_vars(None) is None
        assert _substitute_env_vars(3.14) == 3.14


class TestDeepMergeConfigs:
    def test_scalar_override(self):
        assert deep_merge_configs({"a": 1}, {"a": 2}) == {"a": 2}

    def test_nested_dict_recursive_merge(self):
        base = {"a": {"x": 1, "y": 2}}
        override = {"a": {"y": 3, "z": 4}}
        assert deep_merge_configs(base, override) == {"a": {"x": 1, "y": 3, "z": 4}}

    def test_list_replaced_not_merged(self):
        base = {"a": [1, 2, 3]}
        override = {"a": [9]}
        assert deep_merge_configs(base, override) == {"a": [9]}

    def test_base_not_modified(self):
        base = {"a": {"x": 1}, "l": [1]}
        override = {"a": {"x": 2}, "l": [2]}
        deep_merge_configs(base, override)
        assert base == {"a": {"x": 1}, "l": [1]}

    def test_dict_overridden_by_scalar(self):
        base = {"a": {"x": 1}}
        override = {"a": "scalar"}
        assert deep_merge_configs(base, override) == {"a": "scalar"}

    def test_scalar_overridden_by_dict(self):
        base = {"a": "scalar"}
        override = {"a": {"x": 1}}
        assert deep_merge_configs(base, override) == {"a": {"x": 1}}

    def test_new_key_added(self):
        assert deep_merge_configs({"a": 1}, {"b": 2}) == {"a": 1, "b": 2}

    def test_empty_override_returns_copy(self):
        base = {"a": {"x": 1}}
        result = deep_merge_configs(base, {})
        assert result == base
        assert result is not base


class TestLoadExternalConfig:
    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_external_config(tmp_path / "nope.yaml")

    def test_malformed_yaml_raises(self, tmp_path):
        p = tmp_path / "bad.yaml"
        p.write_text("key: [unclosed", encoding="utf-8")
        with pytest.raises(yaml.YAMLError):
            load_external_config(p)

    def test_non_dict_raises(self, tmp_path):
        p = tmp_path / "scalar.yaml"
        p.write_text("just a string\n", encoding="utf-8")
        with pytest.raises(ValueError):
            load_external_config(p)

    def test_list_content_raises(self, tmp_path):
        p = tmp_path / "list.yaml"
        p.write_text("- 1\n- 2\n", encoding="utf-8")
        with pytest.raises(ValueError):
            load_external_config(p)

    def test_loads_dict(self, tmp_path):
        p = _write_yaml(tmp_path / "ext.yaml", {"llm": {"temperature": 0.9}})
        assert load_external_config(p) == {"llm": {"temperature": 0.9}}

    def test_applies_env_substitution(self, tmp_path, monkeypatch):
        monkeypatch.setenv("EXT_VAR", "secret")
        p = _write_yaml(tmp_path / "ext.yaml", {"api_key": "${EXT_VAR}"})
        assert load_external_config(p) == {"api_key": "secret"}


class TestApplyPerfEnvOverrides:
    def test_all_overrides_applied(self, monkeypatch):
        monkeypatch.setenv("PERF_ENABLED", "true")
        monkeypatch.setenv("PERF_BEAM_SIZE", "7")
        monkeypatch.setenv("PERF_BRANCHES", "8")
        monkeypatch.setenv("PERF_DEPTH", "9")
        monkeypatch.setenv("PERF_DIMENSIONS", "a, b ,,c")
        monkeypatch.setenv("PERF_PRIMARY_DIMENSION", "dim_x")
        monkeypatch.setenv("PERF_TEMPERATURE", "0.75")
        monkeypatch.setenv("PERF_MAX_WORKERS", "5")
        monkeypatch.setenv("PERF_TIMEOUT_NODE", "123")
        monkeypatch.setenv("PERF_TOURNAMENT_SIZE", "4")
        monkeypatch.setenv("PERF_ALWAYS_VERIFY", "false")
        monkeypatch.setenv("PERF_MAX_TOOL_FAILURES", "6")
        monkeypatch.setenv("PERF_FAST_FAILURE_DIAGNOSTICS", "no")
        monkeypatch.setenv("PERF_COQC_TIMEOUT", "321")
        monkeypatch.setenv("PERF_ON_DEMAND_BACKTRACK", "yes")
        monkeypatch.setenv("PERF_REFLECTION_QUALITY_WINDOW", "5")
        monkeypatch.setenv("PERF_MIN_REFLECTION_QUALITY", "0.33")
        monkeypatch.setenv("PERF_MAX_REFLECTION_RETRIES", "9")

        cfg = _apply_perf_env_overrides({})
        perf = cfg["proof"]["perf"]
        assert perf["enabled"] is True
        assert perf["beam_size"] == 7
        assert perf["branches_per_node"] == 8
        assert perf["depth_limit"] == 9
        assert perf["dimensions"] == ["a", "b", "c"]
        assert perf["primary_dimension"] == "dim_x"
        assert perf["generation_temperature"] == 0.75
        assert perf["max_workers"] == 5
        assert perf["timeout_per_node"] == 123
        assert perf["scoring_tournament_size"] == 4
        assert perf["always_verify_children"] is False
        assert perf["max_tool_failures_before_fallback"] == 6
        assert perf["enable_fast_failure_diagnostics"] is False
        assert perf["coqc_timeout"] == 321
        assert perf["backtracking"]["on_demand"]["enabled"] is True
        assert perf["reflection_quality_window"] == 5
        assert perf["min_reflection_quality"] == 0.33
        assert perf["max_reflection_retries"] == 9

    def test_invalid_numeric_values_ignored(self, monkeypatch):
        monkeypatch.setenv("PERF_BEAM_SIZE", "not-a-number")
        monkeypatch.setenv("PERF_TEMPERATURE", "abc")
        monkeypatch.setenv("PERF_DEPTH", "1.5")
        cfg = _apply_perf_env_overrides({})
        perf = cfg["proof"]["perf"]
        assert "beam_size" not in perf
        assert "generation_temperature" not in perf
        assert "depth_limit" not in perf

    def test_boolean_truthy_variants(self, monkeypatch):
        for val in ("true", "1", "yes", "TRUE", "Yes"):
            monkeypatch.setenv("PERF_ENABLED", val)
            cfg = _apply_perf_env_overrides({})
            assert cfg["proof"]["perf"]["enabled"] is True

    def test_boolean_falsy_variants(self, monkeypatch):
        for val in ("false", "0", "no", "FALSE", "anything"):
            monkeypatch.setenv("PERF_ENABLED", val)
            cfg = _apply_perf_env_overrides({})
            assert cfg["proof"]["perf"]["enabled"] is False

    def test_dimensions_trims_and_drops_empty(self, monkeypatch):
        monkeypatch.setenv("PERF_DIMENSIONS", " a ,, b , c ")
        cfg = _apply_perf_env_overrides({})
        assert cfg["proof"]["perf"]["dimensions"] == ["a", "b", "c"]

    def test_dimensions_all_empty_keeps_existing(self, monkeypatch):
        monkeypatch.setenv("PERF_DIMENSIONS", " , , ")
        cfg = _apply_perf_env_overrides({"proof": {"perf": {"dimensions": ["orig"]}}})
        assert cfg["proof"]["perf"]["dimensions"] == ["orig"]

    def test_no_vars_creates_empty_perf_and_returns_same(self):
        cfg = {"proof": {}}
        result = _apply_perf_env_overrides(cfg)
        assert result is cfg
        assert result["proof"] == {"perf": {}}

    def test_primary_dimension_stripped(self, monkeypatch):
        monkeypatch.setenv("PERF_PRIMARY_DIMENSION", "  trace_alignment  ")
        cfg = _apply_perf_env_overrides({})
        assert cfg["proof"]["perf"]["primary_dimension"] == "trace_alignment"


class TestLoadConfig:
    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_config(config_path=tmp_path / "nope.yaml", force_reload=True)

    def test_defaults_injected(self, tmp_path):
        cfg_file = _write_yaml(tmp_path / "config.yaml", {})
        cfg = load_config(config_path=cfg_file, force_reload=True)

        assert cfg["llm"]["temperature"] == 0.2
        assert cfg["llm"]["max_tokens"] == 2048
        assert cfg["llm"]["timeout"] == 120
        assert cfg["llm"]["retries"] == 3

        koika = cfg["provers"]["koika"]
        assert koika["enabled"] is True
        assert koika["lemma_mining"] is True
        assert koika["use_proof_library"] is True
        assert koika["use_mc_lemmas"] is False
        assert koika["prove"]["skill"] == "rocq-mcp"
        assert koika["prove"]["proof_timeout"] == 600
        assert koika["prove"]["coq_tactic_hints"] == [
            "induction", "simpl", "auto", "eauto", "rewrite", "inversion",
            "subst", "destruct", "split", "lia", "nia",
        ]
        assert koika["prove"]["use_rocq_mcp"] is True

        acl2 = cfg["provers"]["acl2"]
        assert acl2["enabled"] is True
        assert acl2["prove"]["skill"] == "acl2_builtin"
        assert acl2["prove"]["hint_classes"] == ["rewrite", "linear", "induct"]

        assert cfg["verification"]["default_backend"] == "koika"
        assert cfg["verification"]["bmc_max_depth"] == 100
        assert cfg["verification"]["ic3_max_steps"] == 1000
        assert cfg["verification"]["simulation_cycles"] == 1000
        assert cfg["verification"]["formal_timeout"] == 300

        perf = cfg["proof"]["perf"]
        assert perf["enabled"] is False
        assert perf["beam_size"] == 3
        assert perf["dimensions"] == [
            "subgoal_reduction", "trace_alignment", "syntactic_purity",
        ]
        assert perf["generation_temperature"] == 0.4

        assert cfg["lifting"]["vcd_parser"] == "builtin"
        assert cfg["lifting"]["llm_lifter_enabled"] is True
        assert cfg["evidence"]["db_path"] == "build/evidence.db"
        assert cfg["evidence"]["auto_commit"] is True
        assert cfg["logging"]["level"] == "INFO"
        assert cfg["directories"]["build"] == "build"
        assert cfg["directories"]["logs"] == "build/logs"

    def test_explicit_values_preserved_over_defaults(self, tmp_path):
        cfg_file = _write_yaml(
            tmp_path / "config.yaml",
            {"llm": {"temperature": 0.9}, "verification": {"bmc_max_depth": 42}},
        )
        cfg = load_config(config_path=cfg_file, force_reload=True)
        assert cfg["llm"]["temperature"] == 0.9
        assert cfg["verification"]["bmc_max_depth"] == 42

    def test_env_substitution_applied(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MY_API_KEY", "k123")
        cfg_file = _write_yaml(tmp_path / "config.yaml", {"api_key": "${MY_API_KEY}"})
        cfg = load_config(config_path=cfg_file, force_reload=True)
        assert cfg["api_key"] == "k123"

    def test_external_config_merged(self, tmp_path):
        main_file = _write_yaml(
            tmp_path / "config.yaml",
            {"llm": {"temperature": 0.5}, "verification": {"bmc_max_depth": 50}},
        )
        ext_file = _write_yaml(
            tmp_path / "ext.yaml",
            {"llm": {"max_tokens": 100}, "verification": {"ic3_max_steps": 500}},
        )
        cfg = load_config(
            config_path=main_file,
            force_reload=True,
            external_config_path=ext_file,
        )
        assert cfg["llm"]["temperature"] == 0.5
        assert cfg["llm"]["max_tokens"] == 100
        assert cfg["verification"]["bmc_max_depth"] == 50
        assert cfg["verification"]["ic3_max_steps"] == 500

    def test_caching_returns_same_object(self, tmp_path):
        cfg_file = _write_yaml(
            tmp_path / "config.yaml", {"verification": {"bmc_max_depth": 123}}
        )
        first = load_config(config_path=cfg_file, force_reload=True)
        other = _write_yaml(
            tmp_path / "other.yaml", {"verification": {"bmc_max_depth": 999}}
        )
        second = load_config(config_path=other, force_reload=False)
        assert second is first
        assert second["verification"]["bmc_max_depth"] == 123

    def test_force_reload_reads_fresh_file(self, tmp_path):
        cfg_file = _write_yaml(
            tmp_path / "config.yaml", {"verification": {"bmc_max_depth": 1}}
        )
        assert load_config(config_path=cfg_file, force_reload=True)["verification"]["bmc_max_depth"] == 1
        _write_yaml(tmp_path / "config.yaml", {"verification": {"bmc_max_depth": 2}})
        assert load_config(config_path=cfg_file, force_reload=True)["verification"]["bmc_max_depth"] == 2

    def test_perf_conflict_raises(self, tmp_path):
        cfg_file = _write_yaml(
            tmp_path / "config.yaml",
            {
                "proof": {"perf": {"enabled": True}},
                "provers": {"koika": {"use_proof_library": True}},
            },
        )
        with pytest.raises(ValueError, match="PERF"):
            load_config(config_path=cfg_file, force_reload=True)

    def test_perf_enabled_without_library_ok(self, tmp_path):
        cfg_file = _write_yaml(
            tmp_path / "config.yaml",
            {
                "proof": {"perf": {"enabled": True}},
                "provers": {"koika": {"use_proof_library": False}},
            },
        )
        cfg = load_config(config_path=cfg_file, force_reload=True)
        assert cfg["proof"]["perf"]["enabled"] is True

    def test_perf_env_override_applied(self, tmp_path, monkeypatch):
        monkeypatch.setenv("PERF_BEAM_SIZE", "11")
        cfg_file = _write_yaml(tmp_path / "config.yaml", {})
        cfg = load_config(config_path=cfg_file, force_reload=True)
        assert cfg["proof"]["perf"]["beam_size"] == 11


class TestGetAndReloadConfig:
    def test_get_config_nested(self, tmp_path):
        cfg_file = _write_yaml(
            tmp_path / "config.yaml", {"verification": {"bmc_max_depth": 7}}
        )
        load_config(config_path=cfg_file, force_reload=True)
        assert get_config("verification.bmc_max_depth") == 7
        assert get_config("verification.default_backend") == "koika"

    def test_get_config_missing_returns_default(self, tmp_path):
        cfg_file = _write_yaml(tmp_path / "config.yaml", {})
        load_config(config_path=cfg_file, force_reload=True)
        assert get_config("missing.key", "fallback") == "fallback"
        assert get_config("missing.key") is None

    def test_get_config_non_dict_intermediate(self, tmp_path):
        cfg_file = _write_yaml(tmp_path / "config.yaml", {})
        load_config(config_path=cfg_file, force_reload=True)
        assert get_config("llm.temperature.nope", "d") == "d"

    def test_get_config_whole_dict(self, tmp_path):
        cfg_file = _write_yaml(
            tmp_path / "config.yaml", {"verification": {"bmc_max_depth": 7}}
        )
        load_config(config_path=cfg_file, force_reload=True)
        whole = get_config()
        assert whole["verification"]["bmc_max_depth"] == 7

    def test_reload_config_uses_specir_config(self, tmp_path, monkeypatch):
        cfg_file = _write_yaml(
            tmp_path / "config.yaml", {"verification": {"bmc_max_depth": 42}}
        )
        monkeypatch.setenv("SPECIR_CONFIG", str(cfg_file))
        cfg = reload_config()
        assert cfg["verification"]["bmc_max_depth"] == 42

    def test_reload_config_forces_reload(self, tmp_path, monkeypatch):
        cfg_file = _write_yaml(
            tmp_path / "config.yaml", {"verification": {"bmc_max_depth": 1}}
        )
        monkeypatch.setenv("SPECIR_CONFIG", str(cfg_file))
        assert load_config(config_path=cfg_file, force_reload=True)["verification"]["bmc_max_depth"] == 1
        _write_yaml(tmp_path / "config.yaml", {"verification": {"bmc_max_depth": 2}})
        assert reload_config()["verification"]["bmc_max_depth"] == 2


class TestFindProjectRoot:
    def test_finds_conf_config_yaml(self, tmp_path, monkeypatch):
        (tmp_path / "conf").mkdir()
        (tmp_path / "conf" / "config.yaml").write_text("{}", encoding="utf-8")
        monkeypatch.setattr(os, "getcwd", lambda: str(tmp_path))
        assert _find_project_root() == tmp_path

    def test_walks_up_to_parent(self, tmp_path, monkeypatch):
        root = tmp_path / "proj"
        (root / "conf").mkdir(parents=True)
        (root / "conf" / "config.yaml").write_text("{}", encoding="utf-8")
        sub = root / "a" / "b"
        sub.mkdir(parents=True)
        monkeypatch.setattr(os, "getcwd", lambda: str(sub))
        assert _find_project_root() == root

    def test_no_marker_returns_cwd(self, tmp_path, monkeypatch):
        monkeypatch.setattr(os, "getcwd", lambda: str(tmp_path))
        assert _find_project_root() == tmp_path
