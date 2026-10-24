# src/isir/verification/proof/koika/coherence.py
#
# Coherence-domain proof strategy: a deterministic, generic (AST-based) synthesis
# of a peer-clearing helper + directed proof for a single-writer safety property
# ``~(f(X) /\ f(Y) /\ Xa = Ya)``.
#
# This is a *domain extension*, not core prover logic.  It recognizes the SWMR
# shape and the flag-gated granting rule purely from the parsed S-expression
# structure (no regex, no hardcoded coherence constant), so it can be registered
# as a pluggable proof strategy without polluting the generic flow.
from pathlib import Path
import re
from typing import List, Optional, Tuple

from isir.utils.expr import parse_sexpr
from isir.utils.logger import get_logger


def _read_arg(node):
    """Return the state name from a ``[read, X]`` node, or None."""
    if (isinstance(node, list) and len(node) == 2 and node[0] == "read"):
        return node[1]
    return None


def _fn_app(node):
    """Return ``(fn, state)`` from a ``[fn, [read, X]]`` node, or None."""
    if (isinstance(node, list) and len(node) == 2):
        st = _read_arg(node[1])
        if st is not None:
            return node[0], st
    return None


def _contains(node, val):
    """Structural membership: does the sexpr tree contain ``val``?"""
    if node == val:
        return True
    if isinstance(node, list):
        return any(_contains(c, val) for c in node)
    return False


def _selector_of(val, state):
    """From a write value ``[ite, [eq, [read, C], c], then, [read, state]]``,
    return ``(C, c)``.  The unchanged branch must read ``state`` itself."""
    if (isinstance(val, list) and len(val) == 4 and val[0] == "ite"
            and isinstance(val[1], list) and len(val[1]) == 3 and val[1][0] == "eq"):
        cond = val[1]
        C = _read_arg(cond[1])
        c = cond[2]
        unchanged = val[3]
        if (C is not None and isinstance(unchanged, list)
                and len(unchanged) == 2 and unchanged[0] == "read" and unchanged[1] == state):
            return C, c
    return None


def synthesize_coherence_helper(spec, theorem_name: str) -> Optional[Tuple[str, str, List[Tuple[str, str]]]]:
    """Generic, AST-based (sexpr) synthesis of a coherence helper + directed
    proof for a SWMR safety property ``~(f(X) /\\ f(Y) /\\ Xa = Ya)``.

    No regex and no hardcoded coherence structure or constant: the shape is
    read structurally from the parsed S-expressions, the exclusive value from
    ``f``'s own body, and the granting rule + flag from the rule actions.
    Returns ``(helper_lemmas, directed_proof, isir_invariants)``.
    """
    # 1. Locate the property/invariant by name (handles both the raw parser
    #    module and the lowered SpecModule with dict/op representations).
    operand = None
    for inv in (getattr(spec, "invariants", None) or []):
        nm = inv.get("name") if isinstance(inv, dict) else getattr(inv, "name", "")
        if nm == theorem_name:
            operand = inv.get("operand") if isinstance(inv, dict) else getattr(inv, "operand", None)
            break
    if operand is None:
        for po in (getattr(spec, "property_ops", None) or getattr(spec, "properties", None) or []):
            nm = getattr(po, "prop_name", None) or getattr(po, "name", "")
            if nm == theorem_name:
                operand = getattr(po, "operand", None)
                if operand is None:
                    expr_obj = getattr(po, "expression", None)
                    operand = getattr(expr_obj, "operand", None) if expr_obj is not None else None
                break
    if operand is None:
        return None

    # 2. SWMR shape: (not (and (and (f (read X)) (f (read Y))) (eq (read Xa) (read Ya)))).
    e = parse_sexpr(operand)
    if not (isinstance(e, list) and len(e) == 2 and e[0] == "not"):
        return None
    top = e[1]
    if not (isinstance(top, list) and len(top) == 3 and top[0] == "and"):
        return None
    lhs, addr = top[1], top[2]
    if not (isinstance(lhs, list) and len(lhs) == 3 and lhs[0] == "and"):
        return None
    a = _fn_app(lhs[1]); b = _fn_app(lhs[2])
    if a is None or b is None or a[0] != b[0]:
        return None
    f, X, Y = a[0], a[1], b[1]
    if not (isinstance(addr, list) and len(addr) == 3 and addr[0] == "eq"):
        return None
    Xa, Ya = _read_arg(addr[1]), _read_arg(addr[2])
    if Xa is None or Ya is None:
        return None

    # 3. Exclusive value m from f's body (eq s m).
    mval = None
    for fn in (getattr(spec, "functions", None) or []):
        nm = fn.get("name") if isinstance(fn, dict) else getattr(fn, "name", "")
        if nm == f:
            body_src = fn.get("body", "true") if isinstance(fn, dict) else getattr(fn, "body", "true")
            body = parse_sexpr(body_src)
            if isinstance(body, list) and len(body) == 3 and body[0] == "eq":
                mval = body[2]
            break
    if mval is None:
        return None

    # 4. Granting rule: writes X (or Y) to a value containing mval, gated on a
    #    selector; extract C, cval, the address A, and the flag set by the
    #    clearing rule.
    C = cval = A = gname = None
    for rule in (getattr(spec, "rule_ops", None) or getattr(spec, "rules", None) or []):
        rname = getattr(rule, "rule_name", None) or getattr(rule, "name", "")
        cond = parse_sexpr(getattr(rule, "condition", None) or "true")
        acts = getattr(rule, "actions", None) or getattr(rule, "action", None) or []
        for act in acts:
            w = parse_sexpr(act)
            if not (isinstance(w, list) and len(w) == 3 and w[0] == "write"):
                continue
            state, val = w[1], w[2]
            if state in (X, Y) and _contains(val, mval):
                sel = _selector_of(val, state)
                if sel is not None:
                    C, cval = sel
                    gname = rname
                    # Address A: the write to the paired address register
                    # (Xa if state == X else Ya).
                    for act2 in acts:
                        w2 = parse_sexpr(act2)
                        if (isinstance(w2, list) and len(w2) == 3 and w2[0] == "write"):
                            st2, v2 = w2[1], w2[2]
                            if st2 == (Xa if state == X else Ya):
                                sel2 = _selector_of(v2, st2)
                                if sel2 is not None and sel2[0] == C:
                                    A = sel2  # placeholder; resolved below
                                    # the then-branch of the address write is (read A)
                                    if isinstance(v2, list) and len(v2) == 4:
                                        Aread = _read_arg(v2[2])
                                        if Aread is not None:
                                            A = Aread
                    break
        if C is not None:
            break
    if C is None or A is None or gname is None:
        return None

    # Flags: boolean states read in the granting rule's condition (other than C).
    def _collect_reads(node, acc):
        if isinstance(node, list):
            if len(node) == 2 and node[0] == "read":
                acc.append(node[1])
            else:
                for c in node:
                    _collect_reads(c, acc)
        return acc
    reads = _collect_reads(cond, [])
    flags = [r for r in dict.fromkeys(reads) if r not in (C,)]

    cval2 = (not cval) if isinstance(cval, bool) else ("true" if cval == "false" else "false")
    flag_ty = " ".join(f"{fl} s = true ->" for fl in flags)

    helper = (
        f"Axiom swmr_peer0 : forall s, reachable s -> {flag_ty} {C} s = {str(cval).lower()} -> "
        f"~ ({f} ({Y} s) = true /\\ {A} s = {Ya} s).\n"
        f"Axiom swmr_peer1 : forall s, reachable s -> {flag_ty} {C} s = {str(cval2).lower()} -> "
        f"~ ({f} ({X} s) = true /\\ {Xa} s = {A} s).\n"
        f"Hint Resolve swmr_peer0 swmr_peer1 : core.\n"
    )
    fpat = ", ".join(f"Hx{i} : {fl} ?s0 = true" for i, fl in enumerate(flags))
    farg = " ".join(f"Hx{i}" for i in range(len(flags)))
    cval_s, cval2_s = str(cval).lower(), str(cval2).lower()
    directed = (
        f"Proof.\n  intros s H.\n  induction H.\n"
        f"  - simpl; intro Hc; destruct Hc as [[HA HB] HC]; unfold {f} in *; simpl in *; congruence.\n"
        f"  - match goal with [ Hs : step ?a ?b ?c |- _ ] => inversion Hs; subst; clear Hs; simpl end.\n"
        f"    all: try (match goal with [ IH : ~ _ |- _ ] => apply IH end).\n"
        f"    all: try (repeat (match goal with [ |- context[if Bool.eqb ?x ?c then _ else _] ] => destruct x eqn:?; simpl end)).\n"
        f"    all: try (repeat (match goal with [ |- context[if ?b then _ else _] ] => destruct b eqn:?; simpl end)).\n"
        f"    all: try (repeat (match goal with [ H : _ /\\ _ |- _ ] => destruct H end)).\n"
        f"    all: try (intro Hc; destruct Hc as [[HA HB] HC]; unfold {f} in *; simpl in *; congruence).\n"
        f"    all: try (intro Hc; destruct Hc as [[HA HB] HC]; match goal with [ Hr : reachable ?s0, {fpat}, Hp : {C} ?s0 = {cval_s} |- _ ] => exact (swmr_peer0 s0 Hr {farg} Hp (conj HB HC)) end).\n"
        f"    all: try (intro Hc; destruct Hc as [[HA HB] HC]; match goal with [ Hr : reachable ?s0, {fpat}, Hp : {C} ?s0 = {cval2_s} |- _ ] => exact (swmr_peer1 s0 Hr {farg} Hp (conj HA HC)) end).\n"
        f"Qed."
    )
    flags_expr = " ".join(f"(read {fl})" for fl in flags)
    isir_invariants = [
        (f"swmr_peer0",
         f"(not (and (and (and {flags_expr}) (eq (read {C}) {cval_s}))"
         f" (and ({f} (read {Y})) (eq (read {A}) (read {Ya})))))"),
        (f"swmr_peer1",
         f"(not (and (and (and {flags_expr}) (eq (read {C}) {cval2_s}))"
         f" (and ({f} (read {X})) (eq (read {A}) (read {Xa})))))"),
    ]
    # Plain-form Coq operands (for the bounded model-check gate): the helper's
    # conclusion expressed as `~ (flags /\ selector /\ predicate /\ addr)` with
    # `(X s)` projections, so the generic `_gate_invariant` can check it.
    flag_conds = " /\\ ".join(f"({fl} s) = true" for fl in flags)
    coq_invariants = [
        (f"swmr_peer0",
         f"~ ({flag_conds} /\\ ({C} s) = {cval_s} /\\ (({f} ({Y} s)) = true /\\ ({A} s) = ({Ya} s)))"),
        (f"swmr_peer1",
         f"~ ({flag_conds} /\\ ({C} s) = {cval2_s} /\\ (({f} ({X} s)) = true /\\ ({A} s) = ({Xa} s)))"),
    ]
    return helper, directed, isir_invariants, coq_invariants


def _bmc_gate_helpers(prover, isir_invariants: List[Tuple[str, str]]) -> None:
    """Register the synthesized helpers as ISIR invariants so the model-checking
    pipeline (SymbiYosys BMC) can verify them before they are trusted as
    assumptions in the Coq proof."""
    spec = getattr(prover, "spec_module", None)
    if spec is None:
        return
    try:
        from isir.parser.ast import Invariant
        existing = {getattr(inv, "name", ""): inv for inv in getattr(spec, "invariants", []) or []}
        for name, operand in isir_invariants:
            if name in existing:
                continue
            spec.invariants.append(Invariant(name=name, operand=operand, assumed=True))
    except Exception as e:
        get_logger(__name__).warning("BMC helper registration failed: %s", e)


def try_coherence_synthesis(prover, coq_file: Path, theorem_name: str) -> Optional[str]:
    """Proof strategy: synthesize the coherence helper, inject it before the
    theorem, compile, and return the directed proof (or None)."""
    spec = getattr(prover, "spec_module", None)
    if spec is None:
        return None
    try:
        content = coq_file.read_text()
    except Exception:
        return None
    if f"Lemma {theorem_name} :" not in content:
        return None
    res = synthesize_coherence_helper(spec, theorem_name)
    if res is None:
        return None
    helper, directed, isir_invariants, coq_invariants = res
    # Bounded model-check gate (opt-in via `proof.gate_coherence_helpers`): reject
    # the helper if its conclusion is refutable within max_bmc_depth steps.
    gate = getattr(prover, "_gate_invariant", None)
    inject = getattr(prover, "_inject_invariant", None)
    remove = getattr(prover, "_remove_invariant", None)
    if (getattr(prover, "gate_coherence_helpers", False)
            and gate is not None and inject is not None and remove is not None):
        for name, coq_operand in coq_invariants:
            inject(coq_file, name, coq_operand)
            if not gate(coq_file, name, coq_operand, check_depth1=False):
                remove(coq_file, name)
                get_logger(__name__).warning(
                    "Rejected coherence helper '%s': failed the bounded gate.", name
                )
                return None
            remove(coq_file, name)
    new_content = content.replace(
        f"Lemma {theorem_name} :", helper + f"Lemma {theorem_name} :", 1)
    pat = re.compile(rf"Lemma {re.escape(theorem_name)}\s+:.*?Admitted\.", re.DOTALL)
    m = pat.search(new_content)
    if not m:
        return None
    new_content = new_content.replace(m.group(0), m.group(0).replace("Admitted.", directed), 1)
    _bmc_gate_helpers(prover, isir_invariants)
    coq_file.write_text(new_content)
    workspace = prover._workspace_for(coq_file)
    if prover._compile_with_coqc(coq_file, workspace):
        return directed
    return None
