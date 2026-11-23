# tests/sat_gate/test_preseed_extraction.py

from isir.verification.sat_gate.epoch_reuse import extract_preseed


def test_preseed_keeps_base_valid_and_inductive():
    widths = {"count": 4}
    init = {"count": 0}
    transitions = {"count": "(add (read count) 1)"}
    # (count <= 8) is base-valid but NOT inductive (8 -> 9); (count <= 15) is both.
    certified = ["(le (read count) 8)", "(le (read count) 15)"]
    preseed = extract_preseed(init, transitions, widths, certified)
    assert preseed == ["(le (read count) 15)"]


def test_preseed_drops_base_invalid():
    widths = {"count": 4}
    init = {"count": 9}  # 9 > 8, so (count <= 8) is base-invalid.
    transitions = {"count": "(add (read count) 0)"}
    certified = ["(le (read count) 8)"]
    assert extract_preseed(init, transitions, widths, certified) == []


def test_preseed_is_subset_of_input():
    widths = {"count": 4}
    init = {"count": 0}
    transitions = {"count": "(add (read count) 1)"}
    certified = ["(le (read count) 3)", "(le (read count) 15)"]
    preseed = extract_preseed(init, transitions, widths, certified)
    assert set(preseed) <= set(certified)
