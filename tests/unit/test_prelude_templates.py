# tests/unit/test_prelude_templates.py
#
# Unit tests for the standard prelude templates in
# `isir.verification.proof.prelude_templates`.  These tests verify that
# the template getter returns non-empty, expected strings for each
# backend and an empty string for unknown backends.

import pytest
from isir.verification.proof.prelude_templates import (
    get_prelude,
    KOIKA_PRELUDE,
    ACL2_PRELUDE,
)


class TestGetPrelude:
    def test_koika_prelude_non_empty(self):
        assert get_prelude("koika").strip() != ""

    def test_koika_prelude_contains_expected_imports(self):
        prelude = get_prelude("koika")
        expected = [
            "Require Import Init.Datatypes.",
            "Require Import Arith.PeanoNat.",
            "Require Import Lists.List.",
            "Require Import Bool.Bool.",
            "Require Import Lia.",
            "Require Import Psatz.",
            "Import ListNotations.",
        ]
        for line in expected:
            assert line in prelude, f"missing line {line!r} in koika prelude"

    def test_koika_prelude_case_insensitive(self):
        assert get_prelude("KOIKA") == get_prelude("koika")

    def test_acl2_prelude_non_empty(self):
        assert get_prelude("acl2").strip() != ""

    def test_acl2_prelude_contains_include_books(self):
        prelude = get_prelude("acl2")
        assert '(in-package "ACL2")' in prelude
        assert "arithmetic-5/top" in prelude
        assert "std/lists/nth" in prelude
        assert "std/lists/update-nth" in prelude

    def test_acl2_prelude_case_insensitive(self):
        assert get_prelude("ACL2") == get_prelude("acl2")

    def test_unknown_backend_returns_empty(self):
        assert get_prelude("lean") == ""

    def test_unknown_backend_with_mixed_case_returns_empty(self):
        assert get_prelude("Coq") == ""

    def test_koika_and_acl2_preludes_differ(self):
        assert get_prelude("koika") != get_prelude("acl2")


def test_module_constants_are_non_empty():
    assert KOIKA_PRELUDE.strip() != ""
    assert ACL2_PRELUDE.strip() != ""


def test_koika_prelude_is_idempotent_text():
    assert KOIKA_PRELUDE.endswith("\n")
    assert ACL2_PRELUDE.endswith("\n")
