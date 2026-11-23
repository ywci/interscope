# tests/sat_gate/test_audit.py

from isir.verification.sat_gate.audit import AuditStore, RunManifest


def test_put_and_get_roundtrip():
    store = AuditStore()
    h = store.put({"kind": "cert", "id": 1})
    assert store.get(h) == {"kind": "cert", "id": 1}


def test_indexes():
    store = AuditStore()
    h1 = store.put({"id": 1}, obligation_id="o1", theorem_id="t1", epoch_hash="e1")
    h2 = store.put({"id": 2}, obligation_id="o1", epoch_hash="e1")
    store.put({"id": 3}, hint_id="h1")
    assert store.for_obligation("o1") == [h1, h2]
    assert store.for_theorem("t1") == [h1]
    assert set(store.for_epoch("e1")) == {h1, h2}
    assert store.provenance("h1") is not None


def test_invalidate_epoch():
    store = AuditStore()
    h = store.put({"id": 1}, epoch_hash="e1")
    store.put({"id": 2}, epoch_hash="e2")
    assert store.invalidate_epoch("e1") == 1
    assert store.get(h) is None
    assert store.for_epoch("e1") == []


def test_run_manifest_roundtrip():
    m = RunManifest(cert_audit_rate=0.1, memory_map_threshold_bits=10)
    assert m.to_dict()["cert_audit_rate"] == 0.1
    assert m.to_dict()["memory_map_threshold_bits"] == 10
