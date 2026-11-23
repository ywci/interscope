# src/isir/verification/sat_gate/symbols.py
#
# Symbol table: name -> variable -> name round-trip for named feedback.

from typing import Dict, Tuple


class SymbolTable:
    """Maps named signals to contiguous variable id ranges.

    Variables are 1-based (matching the DIMACS convention); bit ``i`` of a
    ``width``-bit signal ``name`` occupies ``base + i`` (LSB first).  When a
    ``cnf`` is supplied, ``intern`` allocates from its shared ``next_var``
    counter so signal vars and Tseitin auxiliary vars never collide.
    """

    def __init__(self, cnf=None) -> None:
        self._cnf = cnf
        self._base: Dict[str, int] = {}
        self._var_to_sym: Dict[int, Tuple[str, int]] = {}
        self._own_next: int = 1

    def _alloc(self, n: int) -> int:
        if self._cnf is not None:
            base = self._cnf.next_var
            self._cnf.next_var += n
            return base
        base = self._own_next
        self._own_next += n
        return base

    def intern(self, name: str, width: int) -> int:
        """Return the base var id for ``name`` (allocating ``width`` vars)."""
        if name in self._base:
            return self._base[name]
        w = max(1, width)
        base = self._alloc(w)
        self._base[name] = base
        for i in range(w):
            self._var_to_sym[base + i] = (name, i)
        return base

    def var(self, name: str, bit: int) -> int:
        return self._base[name] + bit

    def symbol(self, var: int) -> Tuple[str, int]:
        """Return (name, bit) for a var id; KeyError if not interned."""
        return self._var_to_sym[var]

    def width(self, name: str) -> int:
        if name not in self._base:
            return 0
        # count contiguous vars belonging to this name
        n = 0
        base = self._base[name]
        while (base + n) in self._var_to_sym and self._var_to_sym[base + n][0] == name:
            n += 1
        return n

    def roundtrip_ok(self, name: str, width: int) -> bool:
        """True iff every bit maps name -> var -> name without collision."""
        if name not in self._base:
            return False
        for i in range(width):
            v = self._base[name] + i
            if self._var_to_sym.get(v) != (name, i):
                return False
        return True

    @property
    def next_var(self) -> int:
        return self._cnf.next_var if self._cnf is not None else self._own_next
