# tests/sat_gate/test_array_instantiation.py

from isir.verification.sat_gate.array_instantiate import (
    ackermann_constraints, ackermannize, array_instantiate, collect_selects,
)


def test_store_expansion():
    # select(store(a, i, v), j) -> ite(i=j, v, select(a, j))
    t = ["select", ["store", "a", "i", "v"], "j"]
    assert ackermannize(t) == ["ite", ["=", "i", "j"], "v", ["select", "a", "j"]]


def test_nested_store_expansion():
    t = ["select", ["store", ["store", "a", "i", "v1"], "k", "v2"], "j"]
    r = ackermannize(t)
    assert r[0] == "ite"
    assert r[1] == ["=", "k", "j"]


def test_collect_selects_after_expansion():
    t = ackermannize(["select", ["store", "a", "i", "v"], "j"])
    selects = collect_selects(t)
    assert ("a", "j") in selects


def test_ackermann_constraints_pairwise():
    selects = [("a", "i"), ("a", "j")]
    constraints = ackermann_constraints(selects, max_pairs=16)
    assert constraints == [["=>", ["=", "i", "j"],
                            ["=", ["select", "a", "i"], ["select", "a", "j"]]]]


def test_pair_cap_falls_back():
    selects = [("a", f"i{k}") for k in range(10)]
    # 10 selects -> 45 pairs > cap.
    assert ackermann_constraints(selects, max_pairs=4) is None


def test_array_instantiate_ok():
    # two selects of the same array -> one consistency pair.
    t, constraints, ok = array_instantiate(
        ["=", ["select", "a", "i"], ["select", "a", "j"]])
    assert ok
    assert constraints == [["=>", ["=", "i", "j"],
                            ["=", ["select", "a", "i"], ["select", "a", "j"]]]]
