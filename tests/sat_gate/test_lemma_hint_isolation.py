# tests/sat_gate/test_lemma_hint_isolation.py

import inspect
from isir.verification.sat_gate.policy import disposition, evidence_action


def test_evidence_action_has_no_hint_input():
    params = inspect.signature(evidence_action).parameters
    assert not any("hint" in name for name in params)


def test_disposition_has_no_hint_input():
    params = inspect.signature(disposition).parameters
    assert not any("hint" in name for name in params)


def test_lemma_hint_module_does_not_import_policy():
    """Architectural invariant : lemma_hint.py MUST NOT import policy."""
    import ast
    import importlib
    spec = importlib.util.find_spec("isir.verification.sat_gate.lemma_hint")
    if spec is None:
        return
    src = __import__("pathlib").Path(spec.origin).read_text()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert node.module != "isir.verification.sat_gate.policy"
        elif isinstance(node, ast.Import):
            assert not any("policy" in a.name for a in node.names)
