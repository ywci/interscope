# src/isir/verification/sat_gate/evaluate.py
#
# Reference evaluator: compute named signal values from primary inputs.
# This is a SEPARATE implementation from the lifter and
# is used by the independent replay oracle.


def evaluate_bitwise(op: str, a: int, b: int) -> int:
    if op == "and":
        return a & b
    if op == "or":
        return a | b
    if op == "xor":
        return a ^ b
    raise ValueError(f"unknown bitwise op {op}")


def evaluate_not(a: int, width: int) -> int:
    return (~a) & ((1 << width) - 1)


def evaluate_eq(a: int, b: int) -> int:
    return 1 if a == b else 0


def evaluate_ite(sel: int, a: int, b: int) -> int:
    return a if sel else b


def evaluate_node(op: str, a: int, b: int, width: int) -> int:
    """Evaluate a gate node's output value from its input values."""
    if op in ("and", "or", "xor"):
        return evaluate_bitwise(op, a, b) & ((1 << width) - 1)
    if op == "not":
        return evaluate_not(a, width)
    if op == "eq":
        return evaluate_eq(a, b)
    if op == "ite":
        return evaluate_ite(a, b, 0)  # a = sel (0/1), b = true-branch value
    raise ValueError(f"unknown op {op}")
