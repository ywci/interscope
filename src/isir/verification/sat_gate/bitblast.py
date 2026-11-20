# src/isir/verification/sat_gate/bitblast.py
#
# Direct bit-blasting with Tseitin encoding (§9.4).  No ABC, no optimization
# that renames named signals; feedback goes through the symbol table.
"""Tseitin bit-blaster for the F_exact gate fragment."""

from typing import Dict, List, Sequence

from isir.verification.sat_gate.symbols import SymbolTable


class CNF:
    """A clause database with a fresh-variable counter (DIMACS 1-based)."""

    def __init__(self) -> None:
        self.clauses: List[List[int]] = []
        self.next_var: int = 1

    def new_var(self) -> int:
        v = self.next_var
        self.next_var += 1
        return v

    def add(self, clause: Sequence[int]) -> None:
        self.clauses.append(list(clause))

    def __len__(self) -> int:
        return len(self.clauses)


class BitBlaster:
    """Encodes ``out ↔ op(args)`` for the gate fragment."""

    def __init__(self) -> None:
        self.cnf = CNF()
        self.symbols = SymbolTable(cnf=self.cnf)

    def gate_and(self, out: int, a: int, b: int) -> None:
        # c ↔ a ∧ b : (¬c∨a)(¬c∨b)(c∨¬a∨¬b)
        self.cnf.add([-out, a])
        self.cnf.add([-out, b])
        self.cnf.add([out, -a, -b])

    def gate_or(self, out: int, a: int, b: int) -> None:
        self.cnf.add([-out, a, b])
        self.cnf.add([out, -a])
        self.cnf.add([out, -b])

    def gate_not(self, out: int, a: int) -> None:
        # c ↔ ¬a : (c∨a)(¬c∨¬a)
        self.cnf.add([out, a])
        self.cnf.add([-out, -a])

    def gate_xor(self, out: int, a: int, b: int) -> None:
        self.cnf.add([-out, -a, -b])
        self.cnf.add([-out, a, b])
        self.cnf.add([out, a, -b])
        self.cnf.add([out, -a, b])

    def blast_bitwise(self, op: str, a: Sequence[int], b: Sequence[int],
                      out: Sequence[int]) -> None:
        """op in {and, or, xor}; a, b, out are LSB-first var lists."""
        assert len(a) == len(b) == len(out)
        for o, x, y in zip(out, a, b):
            if op == "and":
                self.gate_and(o, x, y)
            elif op == "or":
                self.gate_or(o, x, y)
            elif op == "xor":
                self.gate_xor(o, x, y)
            else:
                raise ValueError(f"unknown bitwise op {op}")

    def blast_not(self, a: Sequence[int], out: Sequence[int]) -> None:
        assert len(a) == len(out)
        for o, x in zip(out, a):
            self.gate_not(o, x)

    def blast_eq(self, a: Sequence[int], b: Sequence[int]) -> int:
        """Return a 1-bit var meaning ``a == b`` (bitwise equality)."""
        out = self.cnf.new_var()
        xors = [self.cnf.new_var() for _ in a]
        for t, x, y in zip(xors, a, b):
            self.gate_xor(t, x, y)
        # out ↔ ¬(xor0 ∨ … ∨ xorn)
        or_chain = xors[0]
        for t in xors[1:]:
            nxt = self.cnf.new_var()
            self.gate_or(nxt, or_chain, t)
            or_chain = nxt
        self.gate_not(out, or_chain)
        return out

    def blast_ite(self, sel: int, a: Sequence[int], b: Sequence[int],
                  out: Sequence[int]) -> None:
        """out = sel ? a : b (bitwise mux)."""
        assert len(a) == len(b) == len(out)
        for o, x, y in zip(out, a, b):
            # o = (sel ∧ x) ∨ (¬sel ∧ y)
            t1 = self.cnf.new_var()
            t2 = self.cnf.new_var()
            nsel = self.cnf.new_var()
            self.gate_and(t1, sel, x)
            self.gate_not(nsel, sel)
            self.gate_and(t2, nsel, y)
            self.gate_or(o, t1, t2)

    def const_false(self) -> int:
        """A fresh var fixed to false (unit clause)."""
        v = self.cnf.new_var()
        self.cnf.add([-v])
        return v

    def const_true(self) -> int:
        v = self.cnf.new_var()
        self.cnf.add([v])
        return v

    def blast_add(self, a: Sequence[int], b: Sequence[int],
                  out: Sequence[int]) -> None:
        """out = a + b mod 2^n (ripple carry)."""
        n = len(a)
        assert len(b) == n and len(out) == n
        carry = self.const_false()
        for i in range(n):
            s = self.cnf.new_var()          # a_i xor b_i
            self.gate_xor(s, a[i], b[i])
            self.gate_xor(out[i], s, carry)  # out_i = s xor carry
            t1 = self.cnf.new_var()          # a_i & b_i
            self.gate_and(t1, a[i], b[i])
            t2 = self.cnf.new_var()          # carry & s
            self.gate_and(t2, carry, s)
            c = self.cnf.new_var()           # carry' = t1 | t2
            self.gate_or(c, t1, t2)
            carry = c

    def blast_sub(self, a: Sequence[int], b: Sequence[int],
                  out: Sequence[int]) -> None:
        """out = a - b mod 2^n (two's complement: a + ~b + 1)."""
        n = len(a)
        assert len(b) == n and len(out) == n
        nb = [self.cnf.new_var() for _ in range(n)]
        self.blast_not(b, nb)
        carry = self.const_true()  # fold the +1 into the carry-in
        for i in range(n):
            s = self.cnf.new_var()
            self.gate_xor(s, a[i], nb[i])
            self.gate_xor(out[i], s, carry)
            t1 = self.cnf.new_var()
            self.gate_and(t1, a[i], nb[i])
            t2 = self.cnf.new_var()
            self.gate_and(t2, carry, s)
            c = self.cnf.new_var()
            self.gate_or(c, t1, t2)
            carry = c

    def blast_ult(self, a: Sequence[int], b: Sequence[int]) -> int:
        """Return a 1-bit var meaning ``a < b`` (unsigned): borrow-out of a-b."""
        n = len(a)
        borrow = self.const_false()
        for i in range(n):
            na = self.cnf.new_var()
            self.gate_not(na, a[i])
            t1 = self.cnf.new_var()   # ¬a_i & b_i
            self.gate_and(t1, na, b[i])
            t2 = self.cnf.new_var()   # ¬a_i & borrow
            self.gate_and(t2, na, borrow)
            t3 = self.cnf.new_var()   # b_i & borrow
            self.gate_and(t3, b[i], borrow)
            c1 = self.cnf.new_var()   # t1 | t2
            self.gate_or(c1, t1, t2)
            c = self.cnf.new_var()    # (t1 | t2) | t3
            self.gate_or(c, c1, t3)
            borrow = c
        return borrow

    def blast_ule(self, a: Sequence[int], b: Sequence[int]) -> int:
        """Return a 1-bit var meaning ``a <= b`` (unsigned): NOT (b < a)."""
        gt = self.blast_ult(b, a)
        out = self.cnf.new_var()
        self.gate_not(out, gt)
        return out
