# tests/sat_gate/test_frontend_semantics.py

import textwrap
from isir.parser.parser import parse_isir
from isir.lowering.ast_to_isir import convert_ast_to_isir_module
from isir.verification.sat_gate.isir_bridge import (
    initial_values, transitions_of, widths_of,
)


def _module(yaml_text: str):
    import tempfile
    from pathlib import Path
    with tempfile.NamedTemporaryFile("w", suffix=".isir", delete=False) as f:
        f.write(textwrap.dedent(yaml_text))
        path = Path(f.name)
    try:
        return convert_ast_to_isir_module(parse_isir(path).module)
    finally:
        path.unlink()


CONFLICT = """
isir_version: "0.1"
module:
  name: conflict_test
  state:
    - name: x
      kind: register
      type: "bits<4>"
      initial: 0
  inputs:
    - name: sel
      direction: input
      type: "bool"
  rules:
    - name: r1
      condition: "sel"
      action: ["(write x 1)"]
    - name: r2
      condition: "(not sel)"
      action: ["(write x 2)"]
"""


def test_write_conflict_first_rule_wins():
    spec = _module(CONFLICT)
    t = transitions_of(spec)
    # the outermost ite must be the FIRST rule's condition (sel)
    assert t["x"].startswith("(ite sel")


def test_read_during_write_uses_old_value():
    spec = _module(CONFLICT)
    # the write expressions reference the OLD value via (read x), not the next
    t = transitions_of(spec)
    assert "(read x)" in t["x"]  # the default arm reads the current state


def test_initial_value_extracted():
    spec = _module(CONFLICT)
    assert initial_values(spec) == {"x": 0}
    assert widths_of(spec)["x"] == 4
    assert widths_of(spec)["sel"] == 1
