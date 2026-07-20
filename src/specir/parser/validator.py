# src/specir/parser/validator.py
#
# Validates a .specir YAML dictionary against the JSON Schema.
# Uses the jsonschema library and loads the schema from
# conf/schemas/specir_schema.yaml (a fixed path relative to
# the project root). The schema is cached in memory after
# the first load.

from pathlib import Path
from typing import Any, Dict, Optional

import yaml
from jsonschema import Draft7Validator, ValidationError, SchemaError

from specir.utils.config_loader import get_project_root
from specir.parser.parser import SpecIRParseError
from specir.utils.logger import get_logger

logger = get_logger(__name__)

_SCHEMA: Optional[Dict[str, Any]] = None
_VALIDATOR: Optional[Draft7Validator] = None

_SCHEMA_REL_PATH = "conf/schemas/specir_schema.yaml"


def _load_schema(schema_path: Optional[Path] = None) -> Dict[str, Any]:
    """
    Load the SpecIR JSON Schema from YAML, caching the result.

    Args:
        schema_path: Path to the schema file. If None, uses the default
                     location ``conf/schemas/specir_schema.yaml`` relative
                     to the project root.

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
        schema_path = get_project_root() / _SCHEMA_REL_PATH

    if not schema_path.exists():
        raise FileNotFoundError(f"Schema file not found: {schema_path}")

    with open(schema_path, "r", encoding="utf-8") as f:
        schema = yaml.safe_load(f)

    if not isinstance(schema, dict):
        raise ValueError(f"Schema at {schema_path} must be a dictionary")

    # Validate the schema against the Draft7 meta-schema
    try:
        Draft7Validator.check_schema(schema)
    except SchemaError as e:
        raise ValueError(f"Invalid JSON Schema at {schema_path}: {e}") from e

    _SCHEMA = schema
    return schema


def _get_validator() -> Draft7Validator:
    """
    Return a cached Draft7Validator for the SpecIR schema.
    """
    global _VALIDATOR
    if _VALIDATOR is None:
        schema = _load_schema()
        _VALIDATOR = Draft7Validator(schema)
    return _VALIDATOR


def clear_schema_cache() -> None:
    """
    Clear the cached schema and validator (useful for testing).
    """
    global _SCHEMA, _VALIDATOR
    _SCHEMA = None
    _VALIDATOR = None


def validate_specir(raw_data: Dict[str, Any], max_errors: int = 10) -> None:
    """
    Validate a .specir dictionary against the SpecIR JSON Schema.

    Args:
        raw_data: The loaded YAML dictionary.
        max_errors: Maximum number of validation errors to report.

    Raises:
        SpecIRParseError: If validation fails, with a formatted list of errors.
    """
    validator = _get_validator()
    errors = list(validator.iter_errors(raw_data))

    if not errors:
        return

    error_msgs = []
    for err in errors[:max_errors]:
        path = " -> ".join(str(p) for p in err.absolute_path) if err.absolute_path else "<root>"
        error_msgs.append(f"  {path}: {err.message}")

    summary = f"Schema validation failed with {len(errors)} error(s)"
    if len(errors) > max_errors:
        summary += f" (showing first {max_errors})"

    raise SpecIRParseError(summary + ":\n" + "\n".join(error_msgs))


def validate_specir_file(file_path: Path, max_errors: int = 10) -> None:
    """
    Load and validate a .specir file against the schema.

    Args:
        file_path: Path to the .specir file.
        max_errors: Maximum number of validation errors to report.

    Raises:
        SpecIRParseError: On validation failure.
        FileNotFoundError: If the file does not exist.
    """
    if not file_path.exists():
        raise FileNotFoundError(f"SpecIR file not found: {file_path}")

    with open(file_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    if not isinstance(raw, dict):
        raise SpecIRParseError(f"Root of {file_path} must be a dictionary")

    validate_specir(raw, max_errors=max_errors)
