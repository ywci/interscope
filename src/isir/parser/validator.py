# src/isir/parser/validator.py
#
# Validates a .isir YAML dictionary against the JSON Schema.
# Uses the jsonschema library and loads the schema from
# conf/schemas/isir_schema.yaml (relative to the project root).
# The schema is cached in memory after the first load.

import yaml
from pathlib import Path
from typing import Any, Dict, Optional
from jsonschema import SchemaError
from jsonschema.validators import validator_for
from referencing.exceptions import Unresolvable
from isir.parser.parser import ISIRParseError
from isir.utils.logger import get_logger

logger = get_logger(__name__)

_SCHEMA: Optional[Dict[str, Any]] = None
_VALIDATOR = None

_SCHEMA_REL_PATH = Path("conf") / "schemas" / "isir_schema.yaml"

_PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _default_schema_path() -> Path:
    """Return the default schema path, preferring get_project_root() if present."""
    try:
        from isir.utils.config_loader import get_project_root  # noqa: WPS433
        return Path(get_project_root()) / _SCHEMA_REL_PATH
    except Exception:
        return _PROJECT_ROOT / _SCHEMA_REL_PATH


def _load_schema(schema_path: Optional[Path] = None) -> Dict[str, Any]:
    """
    Load the ISIR JSON Schema from YAML, caching the result.

    Args:
        schema_path: Path to the schema file.  Only honored on the first
            call; subsequent calls return the cached schema regardless.
            Use `clear_schema_cache()` to load a different file.

    Returns:
        Schema as a dictionary.

    Raises:
        FileNotFoundError: If the schema file cannot be found.
        ValueError: If the schema is not a valid JSON Schema.
    """
    global _SCHEMA
    if _SCHEMA is not None:
        return _SCHEMA

    if schema_path is None:
        schema_path = _default_schema_path()

    if not schema_path.exists():
        raise FileNotFoundError(f"Schema file not found: {schema_path}")

    with open(schema_path, "r", encoding="utf-8") as f:
        schema = yaml.safe_load(f)

    if not isinstance(schema, dict):
        raise ValueError(f"Schema at {schema_path} must be a dictionary")

    try:
        Validator = validator_for(schema)
        Validator.check_schema(schema)
    except SchemaError as e:
        raise ValueError(f"Invalid JSON Schema at {schema_path}: {e}") from e

    _SCHEMA = schema
    return schema


def _get_validator():
    """
    Return a cached validator for the ISIR schema.

    The concrete validator class (Draft7Validator, Draft202012Validator, …)
    is chosen from the schema's `$schema` keyword, so `$defs` and other
    Draft 2020-12 features resolve correctly.
    """
    global _VALIDATOR
    if _VALIDATOR is None:
        schema = _load_schema()
        Validator = validator_for(schema)
        _VALIDATOR = Validator(schema)
    return _VALIDATOR


def clear_schema_cache():
    global _SCHEMA, _VALIDATOR
    _SCHEMA = None
    _VALIDATOR = None


def validate_isir(raw_data: Dict[str, Any], max_errors: int = 10):
    """
    Validate a .isir dictionary against the ISIR JSON Schema.

    Args:
        raw_data: The loaded YAML dictionary.
        max_errors: Maximum number of validation errors to report.

    Raises:
        ISIRParseError: If validation fails, with a formatted list of errors.
    """
    validator = _get_validator()
    try:
        errors = list(validator.iter_errors(raw_data))
    except Unresolvable as e:
        raise ISIRParseError(f"Schema reference error: {e}") from e

    if not errors:
        return

    error_msgs = []
    for err in errors[:max_errors]:
        path = (
            " -> ".join(str(p) for p in err.absolute_path)
            if err.absolute_path
            else "<root>"
        )
        error_msgs.append(f"  {path}: {err.message}")

    summary = f"Schema validation failed with {len(errors)} error(s)"
    if len(errors) > max_errors:
        summary += f" (showing first {max_errors})"

    raise ISIRParseError(summary + ":\n" + "\n".join(error_msgs))


def validate_isir_file(file_path: Path, max_errors: int = 10) -> None:
    """
    Load and validate a .isir file against the schema.

    Args:
        file_path: Path to the .isir file.
        max_errors: Maximum number of validation errors to report.

    Raises:
        ISIRParseError: On validation failure.
        FileNotFoundError: If the file does not exist.
    """
    if not file_path.exists():
        raise FileNotFoundError(f"ISIR file not found: {file_path}")

    with open(file_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    if not isinstance(raw, dict):
        raise ISIRParseError(f"Root of {file_path} must be a dictionary")

    validate_isir(raw, max_errors=max_errors)
