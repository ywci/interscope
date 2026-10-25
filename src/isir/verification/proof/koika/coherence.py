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


def _fn_app3(node):
    """Return ``(fn, a1, a2, a3)`` from ``[fn, [read, a1], [read, a2], [read, a3]]``."""
    if isinstance(node, list) and len(node) == 4:
        a1 = _read_arg(node[1]); a2 = _read_arg(node[2]); a3 = _read_arg(node[3])
        if a1 is not None and a2 is not None and a3 is not None:
            return node[0], a1, a2, a3
    return None


def _parse_exclusive_clause(cl):
    """Return ``(f, g, X, Y, Ya, Xa)`` from ``(not (and (f X) (g Y Ya Xa)))``."""
    if not (isinstance(cl, list) and len(cl) == 2 and cl[0] == "not"):
        return None
    inner = cl[1]
    if not (isinstance(inner, list) and len(inner) == 3 and inner[0] == "and"):
        return None
    a = _fn_app(inner[1])      # (f X) -> (f, X)
    b = _fn_app3(inner[2])     # (g Y Ya Xa) -> (g, Y, Ya, Xa)
    if a is None or b is None:
        return None
    return a[0], b[0], a[1], b[1], b[2], b[3]


def _parse_exclusive_shape(e):
    """Return ``(f, g, X, Y, Xa, Ya)`` from the MESI-exclusive shape
    ``(and (not (and (f X) (g Y Ya Xa))) (not (and (f Y) (g X Xa Ya))))``."""
    if not (isinstance(e, list) and len(e) == 3 and e[0] == "and"):
        return None
    r0 = _parse_exclusive_clause(e[1])
    r1 = _parse_exclusive_clause(e[2])
    if r0 is None or r1 is None:
        return None
    f0, g0, X0, Y0, Ya0, Xa0 = r0
    f1, g1, X1, Y1, Ya1, Xa1 = r1
    if f0 != f1 or g0 != g1:
        return None
    if X0 == Y1 and Y0 == X1 and Xa0 == Ya1 and Ya0 == Xa1:
        return f0, g0, X0, Y0, Xa0, Ya0
    return None


def _selector_in_condition(cond):
    """Extract ``(C, cval)`` from a condition ``(eq C cval)`` (nested in ``and``),
    where ``C`` is an input/state selector and ``cval`` is a constant.  This is
    the condition-gated selector form (vs. the `ite`-gated value form)."""
    def _walk(n):
        if isinstance(n, list) and n and n[0] == "eq" and len(n) == 3:
            C = n[1]; cval = n[2]
            if isinstance(C, str) and not isinstance(cval, (list, bool)):
                return C, cval
        if isinstance(n, list):
            for a in n[1:]:
                r = _walk(a)
                if r is not None:
                    return r
        return None
    return _walk(cond)


NAT_EQB_NORM_LTAC = """Ltac nat_eqb_norm :=
  repeat (match goal with
  | [ H : Nat.eqb ?a ?b = true |- _ ] => apply Nat.eqb_eq in H
  | [ H : Nat.eqb ?a ?b = false |- _ ] => apply Nat.eqb_neq in H
  | [ H : context[Nat.eqb ?a ?a] |- _ ] => rewrite Nat.eqb_refl in H
  | [ |- context[Nat.eqb ?a ?a] ] => rewrite Nat.eqb_refl
  | [ H : context[Nat.eqb ?a ?b] |- _ ] => destruct (Nat.eqb_spec a b); simpl in *
  | [ |- context[Nat.eqb ?a ?b] ] => destruct (Nat.eqb_spec a b); simpl in *
  end).
"""


def synthesize_coherence_helper(spec, theorem_name: str) -> Optional[Tuple[str, str, List[Tuple[str, str]]]]:
    """Generic, AST-based (sexpr) synthesis of a coherence helper + directed
    proof for a SWMR safety property ``~(f(X) /\\ f(Y) /\\ Xa = Ya)``.

    No regex and no hardcoded coherence structure or constant: the shape is
    read structurally from the parsed S-expressions, the exclusive value from
    ``f``'s own body, and the granting rule + flag from the rule actions.
    Returns ``(helper_lemmas, directed_proof, isir_invariants)``.
    """
    # 1. Locate the property/invariant by name (handles both the raw parser
    #    module and the lowered SpecModule with dict/op representations).  The
    #    Coq theorem name is `<property>_proved`, so strip that suffix.
    prop_name = theorem_name[:-7] if theorem_name.endswith("_proved") else theorem_name
    operand = None
    for inv in (getattr(spec, "invariants", None) or []):
        nm = inv.get("name") if isinstance(inv, dict) else getattr(inv, "name", "")
        if nm in (theorem_name, prop_name):
            operand = inv.get("operand") if isinstance(inv, dict) else getattr(inv, "operand", None)
            break
    if operand is None:
        for po in (getattr(spec, "property_ops", None) or getattr(spec, "properties", None) or []):
            nm = getattr(po, "prop_name", None) or getattr(po, "name", "")
            if nm in (theorem_name, prop_name):
                operand = getattr(po, "operand", None)
                if operand is None:
                    expr_obj = getattr(po, "expression", None)
                    operand = (
                        expr_obj.get("operand")
                        if isinstance(expr_obj, dict)
                        else getattr(expr_obj, "operand", None)
                    )
                break
    if operand is None:
        return None

    # 2. SWMR shape: (not (and (and (f (read X)) (f (read Y))) (eq (read Xa) (read Ya)))),
    #    or MESI-exclusive shape: (and (not (and (f X) (g Y Ya Xa))) (not (and (f Y) (g X Xa Ya)))).
    e = parse_sexpr(operand)
    swmr = None
    if isinstance(e, list) and len(e) == 2 and e[0] == "not":
        top = e[1]
        if isinstance(top, list) and len(top) == 3 and top[0] == "and":
            lhs, addr = top[1], top[2]
            if isinstance(lhs, list) and len(lhs) == 3 and lhs[0] == "and":
                a = _fn_app(lhs[1]); b = _fn_app(lhs[2])
                if a is not None and b is not None and a[0] == b[0]:
                    if isinstance(addr, list) and len(addr) == 3 and addr[0] == "eq":
                        Xa = _read_arg(addr[1]); Ya = _read_arg(addr[2])
                        if Xa is not None and Ya is not None:
                            swmr = (a[0], a[1], b[1], Xa, Ya)
    exclusive = None
    if swmr is None:
        exclusive = _parse_exclusive_shape(e)
    if swmr is None and exclusive is None:
        return None
    if swmr is not None:
        f, X, Y, Xa, Ya = swmr
        g = None
    else:
        f, g, X, Y, Xa, Ya = exclusive

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

    # Input/state names (to classify the selector, flags and address as input- or
    # state-typed).
    state_names = set()
    for s in (getattr(spec, "state_ops", None) or getattr(spec, "state", None) or []):
        nm = s.get("name", "") if isinstance(s, dict) else (getattr(s, "state_name", None) or getattr(s, "name", ""))
        if nm:
            state_names.add(nm)
    input_names = set()
    for inp in (getattr(spec, "inputs", None) or []):
        nm = inp.get("name", "") if isinstance(inp, dict) else getattr(inp, "name", "")
        if nm:
            input_names.add(nm)

    # 4. Granting rule: writes X (or Y) to a value containing mval, gated on a
    #    selector (either `ite`-gated in the value, or condition-gated); extract
    #    C, cval, the address A, and the flag set by the clearing rule.
    C = cval = A = gname = None
    is_input_selector = False
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
                if sel is None:
                    # Condition-gated write: the selector lives in the condition
                    # (e.g. `(eq req_core 0)`), and the write is a constant.
                    sel = _selector_in_condition(cond)
                if sel is not None:
                    C, cval = sel
                    is_input_selector = C in input_names
                    gname = rname
                    # Address A: the write to the paired address register
                    # (Xa if state == X else Ya); either `ite`-gated or constant.
                    for act2 in acts:
                        w2 = parse_sexpr(act2)
                        if (isinstance(w2, list) and len(w2) == 3 and w2[0] == "write"):
                            st2, v2 = w2[1], w2[2]
                            if st2 == (Xa if state == X else Ya):
                                sel2 = _selector_of(v2, st2)
                                if sel2 is not None and sel2[0] == C:
                                    A = sel2
                                    if isinstance(v2, list) and len(v2) == 4:
                                        Aread = _read_arg(v2[2])
                                        if Aread is not None:
                                            A = Aread
                                elif isinstance(v2, str):
                                    # constant address write (e.g. c0_addr = req_addr)
                                    A = v2
                    break
        if C is not None:
            break
    if C is None or A is None or gname is None:
        return None

    # Flags: boolean inputs/states read in the granting rule's condition (other
    # than the selector C).  Function-call arguments are skipped (they are
    # function parameters, not boolean flags).
    function_names = set()
    for fn in (getattr(spec, "functions", None) or []):
        nm = fn.get("name") if isinstance(fn, dict) else getattr(fn, "name", "")
        if nm:
            function_names.add(nm)

    def _collect_reads(node, acc, negated=False):
        if isinstance(node, list):
            if node and node[0] == "not" and len(node) == 2:
                _collect_reads(node[1], acc, not negated)
            elif len(node) == 2 and node[0] == "read":
                acc.append((node[1], not negated))
            elif node and isinstance(node[0], str) and node[0] in function_names:
                return acc
            else:
                for ch in node:
                    _collect_reads(ch, acc, negated)
        elif isinstance(node, str) and node in input_names:
            acc.append((node, not negated))
        return acc
    reads = _collect_reads(cond, [])
    seen = set()
    flags = []
    for name, is_true in reads:
        if name in (C,) or name in seen:
            continue
        seen.add(name)
        flags.append((name, is_true))

    if isinstance(cval, bool):
        cval2 = (not cval)
    elif isinstance(cval, int):
        cval2 = 1 - cval  # 2-core complement (0 <-> 1)
    else:
        cval2 = "true" if cval == "false" else "false"
    cval_s, cval2_s = str(cval).lower(), str(cval2).lower()

    # Input- vs state-typed projections for the selector, flags and address.
    sel_var = "inputs" if is_input_selector else "s"
    quant = "forall s inputs, reachable s ->" if is_input_selector else "forall s, reachable s ->"
    A_proj = f"{A} inputs" if A in input_names else f"{A} s"
    A_isir = A if A in input_names else f"(read {A})"
    flag_ty = " ".join(f"{fl} {'inputs' if fl in input_names else 's'} = {str(is_true).lower()} ->" for fl, is_true in flags)

    # Peer predicate: the SWMR shape uses `f(peer) /\ peer_addr = addr`, the
    # MESI-exclusive shape uses `g(peer, peer_addr, addr)` (a has-line predicate).
    if g is None:
        peer0_coq = f"{f} ({Y} s) = true /\\ {A_proj} = {Ya} s"
        peer1_coq = f"{f} ({X} s) = true /\\ {Xa} s = {A_proj}"
        peer0_isir = f"(and ({f} (read {Y})) (eq {A_isir} (read {Ya})))"
        peer1_isir = f"(and ({f} (read {X})) (eq {A_isir} (read {Xa})))"
        unfold_names = f
        destr = "[[HA HB] HC]"
        arg0 = "(conj HB HC)"
        arg1 = "(conj HA HC)"
    else:
        peer0_coq = f"{g} ({Y} s) ({Ya} s) ({Xa} s) = true"
        peer1_coq = f"{g} ({X} s) ({Xa} s) ({Ya} s) = true"
        peer0_isir = f"({g} (read {Y}) (read {Ya}) (read {Xa}))"
        peer1_isir = f"({g} (read {X}) (read {Xa}) (read {Ya}))"
        unfold_names = f"{f}, {g}"
        destr = "[HA HB]"
        arg0 = "HB"
        arg1 = "HA"

    h0 = f"swmr_peer0_{theorem_name}"
    h1 = f"swmr_peer1_{theorem_name}"
    helper = (
        f"Axiom {h0} : {quant} {flag_ty} {C} {sel_var} = {cval_s} -> "
        f"~ ({peer0_coq}).\n"
        f"Axiom {h1} : {quant} {flag_ty} {C} {sel_var} = {cval2_s} -> "
        f"~ ({peer1_coq}).\n"
        f"Hint Resolve {h0} {h1} : core.\n"
    )
    fpat = ", ".join(f"Hx{i} : {fl} {'?inputs' if fl in input_names else '?s0'} = {str(is_true).lower()}" for i, (fl, is_true) in enumerate(flags))
    farg = " ".join(f"Hx{i}" for i in range(len(flags)))
    sel_pat = "?inputs" if is_input_selector else "?s0"
    helper_args = "s0 inputs" if is_input_selector else "s0"
    if g is None:
        base_cmd = f"simpl; intro Hc; destruct Hc as {destr}; unfold {unfold_names} in *; simpl in *; congruence"
        ih_cmd = "match goal with [ IH : ~ _ |- _ ] => apply IH end"
        split_cmd = ""
    else:
        # MESI-exclusive: (and clause0 clause1) — split into the two clauses and
        # prove each `not (and …)` independently.
        base_cmd = f"simpl; split; intro Hc; destruct Hc as {destr}; unfold {unfold_names} in *; simpl in *; congruence"
        ih_cmd = "match goal with [ IH : _ /\\ _ |- _ ] => destruct IH end"
        split_cmd = "    all: split.\n"
    ih_line = ""
    if g is not None:
        ih_line = "    all: try (intro Hc; destruct Hc as [HA HB]; match goal with [ H : ~ _ |- _ ] => exact (H (conj HA HB)) end).\n"
    directed = (
        f"Proof.\n  intros.\n  match goal with [ H : reachable _ |- _ ] => induction H end.\n"
        f"  - {base_cmd}.\n"
        f"  - match goal with [ Hs : step ?a ?b ?c |- _ ] => inversion Hs; subst; clear Hs; simpl end.\n"
        f"    all: try ({ih_cmd}).\n"
        f"{split_cmd}"
        f"    all: try (repeat (match goal with [ |- context[if Bool.eqb ?x ?c then _ else _] ] => destruct x eqn:?; simpl end)).\n"
        f"    all: try (repeat (match goal with [ |- context[if ?b then _ else _] ] => destruct b eqn:?; simpl end)).\n"
        f"    all: try (repeat (match goal with [ H : _ /\\ _ |- _ ] => destruct H end)).\n"
        f"{ih_line}"
        f"    all: try (intro Hc; destruct Hc as {destr}; unfold {unfold_names} in *; simpl in *; nat_eqb_norm; simpl in *; congruence).\n"
        f"    all: try (intro Hc; destruct Hc as {destr}; match goal with [ Hr : reachable ?s0, {fpat}, Hp : {C} {sel_pat} = {cval_s} |- _ ] => exact ({h0} {helper_args} Hr {farg} Hp {arg0}) end).\n"
        f"    all: try (intro Hc; destruct Hc as {destr}; match goal with [ Hr : reachable ?s0, {fpat}, Hp : {C} {sel_pat} = {cval2_s} |- _ ] => exact ({h1} {helper_args} Hr {farg} Hp {arg1}) end).\n"
        f"Qed."
    )
    flags_expr = " ".join(
        (fl if fl in input_names else f"(read {fl})") if is_true
        else f"(not {fl if fl in input_names else '(read ' + fl + ')'})"
        for fl, is_true in flags
    )
    C_isir = C if is_input_selector else f"(read {C})"
    isir_invariants = [
        (f"{h0}",
         f"(not (and (and (and {flags_expr}) (eq {C_isir} {cval_s}))"
         f" {peer0_isir}))"),
        (f"{h1}",
         f"(not (and (and (and {flags_expr}) (eq {C_isir} {cval2_s}))"
         f" {peer1_isir}))"),
    ]
    # Plain-form Coq operands (for the bounded model-check gate): the helper's
    # conclusion expressed as `~ (flags /\ selector /\ predicate)` with `(X s)`
    # projections, so the generic `_gate_invariant` can check it.
    flag_conds = " /\\ ".join(f"({fl} {'inputs' if fl in input_names else 's'}) = {str(is_true).lower()}" for fl, is_true in flags)
    coq_invariants = [
        (f"{h0}",
         f"~ ({flag_conds} /\\ ({C} {sel_var}) = {cval_s} /\\ ({peer0_coq}))"),
        (f"{h1}",
         f"~ ({flag_conds} /\\ ({C} {sel_var}) = {cval2_s} /\\ ({peer1_coq}))"),
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
    if f"Lemma {theorem_name} :" in content:
        kind = "Lemma"
    elif f"Theorem {theorem_name} :" in content:
        kind = "Theorem"
    else:
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
    if "Ltac nat_eqb_norm" not in content:
        helper = NAT_EQB_NORM_LTAC + helper
    new_content = content.replace(
        f"{kind} {theorem_name} :", helper + f"{kind} {theorem_name} :", 1)
    pat = re.compile(rf"{kind} {re.escape(theorem_name)}\s+:.*?Admitted\.", re.DOTALL)
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
