# tests/unit/test_validator.py
#
# Unit tests for the .isir JSON-Schema validator
# (src/isir/parser/validator.py).

import pytest
from pathlib import Path
from isir.parser import validator
from isir.parser.parser import ISIRParseError


def minimal_isir():
    """Return a fresh, valid minimal .isir dictionary.

    A fresh dict is returned on every call so tests can mutate their own
    copy without leaking state into other tests.
    """
    return {
        "isir_version": "0.1",
        "module": {
            "name": "minimal",
            "clocks": [],
            "resets": [],
            "state": [],
            "rules": [],
        },
    }


@pytest.fixture(autouse=True)
def _fresh_schema_cache():
    """Isolate each test from the module-level schema/validator cache."""
    validator.clear_schema_cache()
    yield
    validator.clear_schema_cache()


def test_valid_minimal_isir_passes():
    """A minimal valid .isir dict validates without raising and returns None."""
    assert validator.validate_isir(minimal_isir()) is None


def test_valid_rich_isir_passes():
    """A fuller valid dict (clocks, resets, state, rules, schedule) passes."""
    data = minimal_isir()
    data["module"].update({
        "clocks": [{"name": "clk", "edge": "posedge", "period": "10ns"}],
        "resets": [
            {"name": "rst", "polarity": "active_high", "async": False, "affects": "all"}
        ],
        "inputs": [{"name": "in", "direction": "input", "type": "bits<8>"}],
        "outputs": [{"name": "out", "direction": "output", "type": "bits<8>"}],
        "state": [{"name": "reg", "kind": "register", "type": "bits<8>", "initial": 0}],
        "rules": [
            {
                "name": "inc",
                "condition": "true",
                "action": ["(write reg (add (read reg) 1))"],
                "priority": 1,
                "attributes": ["atomic", "split"],
            }
        ],
        "schedule": {
            "kind": "conflict_free",
            "conflict_sets": [["inc"]],
        },
    })
    assert validator.validate_isir(data) is None


def test_missing_isir_version_raises():
    data = minimal_isir()
    del data["isir_version"]
    with pytest.raises(ISIRParseError) as exc:
        validator.validate_isir(data)
    assert "isir_version" in str(exc.value)
    assert "required" in str(exc.value)


def test_missing_module_raises():
    data = minimal_isir()
    del data["module"]
    with pytest.raises(ISIRParseError) as exc:
        validator.validate_isir(data)
    assert "module" in str(exc.value)


def test_missing_module_name_raises():
    data = minimal_isir()
    del data["module"]["name"]
    with pytest.raises(ISIRParseError) as exc:
        validator.validate_isir(data)
    assert "name" in str(exc.value)
    assert "module" in str(exc.value)


def test_missing_module_clocks_raises():
    data = minimal_isir()
    del data["module"]["clocks"]
    with pytest.raises(ISIRParseError) as exc:
        validator.validate_isir(data)
    assert "clocks" in str(exc.value)


def test_isir_version_wrong_type_raises():
    data = minimal_isir()
    data["isir_version"] = 0.1
    with pytest.raises(ISIRParseError) as exc:
        validator.validate_isir(data)
    assert "string" in str(exc.value)


def test_module_wrong_type_raises():
    data = minimal_isir()
    data["module"] = "not-a-dict"
    with pytest.raises(ISIRParseError) as exc:
        validator.validate_isir(data)
    assert "object" in str(exc.value)


def test_state_wrong_type_raises():
    data = minimal_isir()
    data["module"]["state"] = "not-an-array"
    with pytest.raises(ISIRParseError) as exc:
        validator.validate_isir(data)
    assert "array" in str(exc.value)


def test_rules_wrong_type_raises():
    data = minimal_isir()
    data["module"]["rules"] = "not-an-array"
    with pytest.raises(ISIRParseError) as exc:
        validator.validate_isir(data)
    assert "array" in str(exc.value)


def test_rule_priority_wrong_type_raises():
    data = minimal_isir()
    data["module"]["rules"] = [{"name": "r", "priority": "high"}]
    with pytest.raises(ISIRParseError) as exc:
        validator.validate_isir(data)
    assert "integer" in str(exc.value)


def test_bad_version_pattern_raises():
    data = minimal_isir()
    data["isir_version"] = "1.0"
    with pytest.raises(ISIRParseError) as exc:
        validator.validate_isir(data)
    assert "isir_version" in str(exc.value)


def test_bad_clock_edge_raises():
    data = minimal_isir()
    data["module"]["clocks"] = [{"name": "clk", "edge": "both_edges"}]
    with pytest.raises(ISIRParseError) as exc:
        validator.validate_isir(data)
    assert "posedge" in str(exc.value)
    assert "negedge" in str(exc.value)


def test_bad_reset_polarity_raises():
    data = minimal_isir()
    data["module"]["resets"] = [
        {"name": "rst", "polarity": "sometimes", "async": False, "affects": "all"}
    ]
    with pytest.raises(ISIRParseError) as exc:
        validator.validate_isir(data)
    assert "active_high" in str(exc.value)


def test_bad_rule_attribute_raises():
    data = minimal_isir()
    data["module"]["rules"] = [{"name": "r", "attributes": ["frobnicate"]}]
    with pytest.raises(ISIRParseError) as exc:
        validator.validate_isir(data)
    assert "split" in str(exc.value)


def test_bad_schedule_kind_raises():
    data = minimal_isir()
    data["module"]["schedule"] = {"kind": "round_robin"}
    with pytest.raises(ISIRParseError) as exc:
        validator.validate_isir(data)
    assert "conflict_free" in str(exc.value)


def test_bad_module_name_pattern_raises():
    data = minimal_isir()
    data["module"]["name"] = "1starts_with_digit"
    with pytest.raises(ISIRParseError) as exc:
        validator.validate_isir(data)
    assert "name" in str(exc.value)


def test_sequential_schedule_requires_rule_order():
    data = minimal_isir()
    data["module"]["schedule"] = {"kind": "sequential"}
    with pytest.raises(ISIRParseError) as exc:
        validator.validate_isir(data)
    assert "rule_order" in str(exc.value)


def test_conflict_free_schedule_requires_conflict_sets():
    data = minimal_isir()
    data["module"]["schedule"] = {"kind": "conflict_free"}
    with pytest.raises(ISIRParseError) as exc:
        validator.validate_isir(data)
    assert "conflict_sets" in str(exc.value)


def test_unknown_top_level_property_is_tolerated():
    """Top-level objects do not set additionalProperties: false."""
    data = minimal_isir()
    data["my_custom_field"] = 12345
    assert validator.validate_isir(data) is None


def test_unknown_module_property_is_tolerated():
    data = minimal_isir()
    data["module"]["my_custom_field"] = {"anything": True}
    assert validator.validate_isir(data) is None


def test_unknown_property_in_adaptive_branching_raises():
    """The nested perf.adaptive_branching object *does* forbid extra keys."""
    data = minimal_isir()
    data["module"]["proof_obligations"] = [
        {
            "property": "p",
            "engine": "simulation",
            "metadata": {
                "perf": {"adaptive_branching": {"enabled": True, "bogus_key": 1}}
            },
        }
    ]
    with pytest.raises(ISIRParseError):
        validator.validate_isir(data)


def test_error_message_includes_json_path():
    data = minimal_isir()
    data["module"]["clocks"] = [{"name": "clk", "edge": "bogus"}]
    with pytest.raises(ISIRParseError) as exc:
        validator.validate_isir(data)
    assert "module -> clocks -> 0 -> edge" in str(exc.value)


def test_error_message_counts_all_errors():
    data = minimal_isir()
    data["module"]["clocks"] = [{"name": "clk", "edge": "bogus"}]
    data["module"]["rules"] = [{"name": "r", "attributes": ["bogus"]}]
    with pytest.raises(ISIRParseError) as exc:
        validator.validate_isir(data)
    assert "2 error(s)" in str(exc.value)


def test_max_errors_truncates_report():
    data = minimal_isir()
    data["module"]["name"] = "1bad"
    data["module"]["clocks"] = [{"name": "clk", "edge": "bogus"}]
    data["module"]["state"] = "not-an-array"
    with pytest.raises(ISIRParseError) as exc:
        validator.validate_isir(data, max_errors=2)
    assert "showing first 2" in str(exc.value)
    body = str(exc.value).split("\n", 1)[1]
    assert len(body.strip().splitlines()) == 2


def test_schema_is_cached():
    first = validator._load_schema()
    second = validator._load_schema()
    assert first is second


def test_schema_path_ignored_after_first_load():
    """After the schema is cached, a different path argument is ignored."""
    validator._load_schema()
    cached = validator._load_schema(schema_path=Path("/nonexistent/other.yaml"))
    assert cached is validator._SCHEMA


def test_validator_is_cached():
    v1 = validator._get_validator()
    v2 = validator._get_validator()
    assert v1 is v2


def test_clear_schema_cache_resets_both():
    validator._load_schema()
    validator._get_validator()
    assert validator._SCHEMA is not None
    assert validator._VALIDATOR is not None

    validator.clear_schema_cache()
    assert validator._SCHEMA is None
    assert validator._VALIDATOR is None


def test_load_schema_file_not_found():
    with pytest.raises(FileNotFoundError):
        validator._load_schema(schema_path=Path("/nonexistent/isir_schema.yaml"))


def test_load_schema_non_dict_raises(tmp_path):
    p = tmp_path / "list_schema.yaml"
    p.write_text("- just\n- a\n- list\n", encoding="utf-8")
    with pytest.raises(ValueError, match="must be a dictionary"):
        validator._load_schema(schema_path=p)


def test_load_schema_invalid_json_schema_raises(tmp_path):
    p = tmp_path / "bad_schema.yaml"
    p.write_text("type: not_a_real_type\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid JSON Schema"):
        validator._load_schema(schema_path=p)


def test_validate_isir_file_valid(tmp_path):
    import yaml

    p = tmp_path / "valid.isir"
    p.write_text(yaml.safe_dump(minimal_isir()), encoding="utf-8")
    assert validator.validate_isir_file(p) is None


def test_validate_isir_file_not_found():
    with pytest.raises(FileNotFoundError):
        validator.validate_isir_file(Path("/nonexistent/file.isir"))


def test_validate_isir_file_non_dict_root(tmp_path):
    p = tmp_path / "list_root.isir"
    p.write_text("- a\n- b\n", encoding="utf-8")
    with pytest.raises(ISIRParseError, match="must be a dictionary"):
        validator.validate_isir_file(p)


def test_validate_isir_file_invalid_content(tmp_path):
    import yaml

    data = minimal_isir()
    del data["isir_version"]
    p = tmp_path / "invalid.isir"
    p.write_text(yaml.safe_dump(data), encoding="utf-8")
    with pytest.raises(ISIRParseError):
        validator.validate_isir_file(p)
