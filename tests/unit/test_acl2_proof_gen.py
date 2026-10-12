# tests/unit/test_acl2_proof_gen.py
#
# Unit tests for ACL2 proof-generation helpers: prompt builders, LLM
# response extraction, hint parsing, and variant generation.  Uses a
# fake LLM client so no real LLM or ACL2 process is needed.

from isir.verification.proof.acl2.proof_gen import (
    get_skeleton_hint,
    build_acl2_proof_prompt,
    build_acl2_hint_prompt,
    build_acl2_reflection_prompt,
    generate_acl2_proof,
    generate_acl2_hints,
    extract_acl2_proof,
    parse_hints_from_response,
    generate_acl2_proof_variants,
    _parse_acl2_repair_variants_response,
)


class FakeLLMClient:
    """Minimal stand-in for LLMClient with mutable temperature/max_tokens."""

    def __init__(self, response="", responses=None):
        self.temperature = 0.2
        self.max_tokens = 2048
        self._default = response
        self._queue = list(responses) if responses is not None else None
        self.calls = []

    def generate(self, prompt, max_tokens=None, **kwargs):
        self.calls.append((prompt, self.max_tokens, max_tokens))
        if self._queue is not None:
            return self._queue.pop(0) if self._queue else self._default
        return self._default


VALID_DEFTHM = (
    "(defthm my-thm\n"
    "  (implies (full st) (not (enqueue st)))\n"
    "  :hints ((\"Goal\" :induct t)))"
)


def test_get_skeleton_hint():
    assert get_skeleton_hint() == ['("Goal" :induct t)']


def test_build_proof_prompt_basic():
    prompt = build_acl2_proof_prompt(
        "no-overflow", "(implies (full st) (not (enqueue st)))"
    )
    assert "(defthm no-overflow" in prompt
    assert "(implies (full st) (not (enqueue st)))" in prompt
    assert "Suggested hint classes: rewrite, linear, induct" in prompt
    assert ":hints" in prompt
    assert "Return ONLY the defthm form" in prompt


def test_build_proof_prompt_with_context():
    prompt = build_acl2_proof_prompt(
        "t", "stmt", context="(defun full (st) ...)"
    )
    assert "Available definitions / lemmas:" in prompt
    assert "(defun full (st) ...)" in prompt


def test_build_proof_prompt_with_assumptions():
    prompt = build_acl2_proof_prompt(
        "t", "stmt", assumptions=["a1", "a2"]
    )
    assert "Assumptions:" in prompt
    assert "Assumption: a1" in prompt
    assert "Assumption: a2" in prompt


def test_build_proof_prompt_with_strategy_hint():
    prompt = build_acl2_proof_prompt(
        "t", "stmt", strategy_hint="use induction"
    )
    assert "**Proof strategy to use:** use induction" in prompt


def test_build_proof_prompt_with_custom_hint_classes():
    prompt = build_acl2_proof_prompt(
        "t", "stmt", hint_classes=["rewrite", "linear"]
    )
    assert "Suggested hint classes: rewrite, linear" in prompt


def test_build_proof_prompt_empty_hint_classes_falls_back():
    prompt = build_acl2_proof_prompt("t", "stmt", hint_classes=[])
    assert "Suggested hint classes: rewrite, linear, induct" in prompt


def test_build_proof_prompt_previous_attempts_limited_to_three():
    attempts = [
        {"script": "(defthm t stmt :hints (a))", "error": "err0"},
        {"script": "(defthm t stmt :hints (b))", "error": "err1"},
        {"script": "(defthm t stmt :hints (c))", "error": "err2"},
        {"script": "(defthm t stmt :hints (d))", "error": "err3"},
    ]
    prompt = build_acl2_proof_prompt("t", "stmt", previous_attempts=attempts)
    assert "Previous attempts failed" in prompt
    assert ":hints (a)" not in prompt
    assert ":hints (b)" in prompt
    assert ":hints (c)" in prompt
    assert ":hints (d)" in prompt
    assert "Please correct the proof" in prompt


def test_build_hint_prompt_basic():
    prompt = build_acl2_hint_prompt(
        "(implies (full st) (not (enqueue st)))", "some ACL2 error"
    )
    assert "(implies (full st) (not (enqueue st)))" in prompt
    assert "some ACL2 error" in prompt
    assert "Previous hints: none" in prompt
    assert "Return ONLY the hint list" in prompt


def test_build_hint_prompt_with_old_hints_and_context():
    prompt = build_acl2_hint_prompt(
        "stmt", "err", old_hints=['("Goal" :induct t)'], context="ctx"
    )
    assert 'Previous hints: ("Goal" :induct t)' in prompt
    assert "ctx" in prompt


def test_build_reflection_prompt_basic():
    prompt = build_acl2_reflection_prompt(
        "my-thm", "stmt", ['("Goal" :induct t)'], "last error"
    )
    assert "my-thm" in prompt
    assert "stmt" in prompt
    assert '("Goal" :induct t)' in prompt
    assert "last error" in prompt
    assert "fundamentally different approach" in prompt


def test_build_reflection_prompt_with_previous_attempts():
    attempts = [{"script": "h1", "error": "e1"}]
    prompt = build_acl2_reflection_prompt(
        "my-thm", "stmt", ["h"], "err", previous_attempts=attempts
    )
    assert "Previous attempts:" in prompt
    assert "h1" in prompt
    assert "e1" in prompt


def test_extract_proof_returns_defthm():
    response = "Here is a proof:\n" + VALID_DEFTHM + "\nMore text"
    out = extract_acl2_proof(response)
    assert out == VALID_DEFTHM


def test_extract_proof_returns_whole_response_when_no_defthm():
    response = "no defthm here at all"
    assert extract_acl2_proof(response) == response


def test_extract_proof_stops_at_balanced_parens():
    response = "(defthm t\n  (equal 1 1))\n(trailing garbage)"
    out = extract_acl2_proof(response)
    assert out == "(defthm t\n  (equal 1 1))"


def test_extract_proof_unbalanced_is_kept_whole():
    response = "(defthm t\n  (equal 1 1)\n  :hints ((\"Goal\" :induct t))"
    out = extract_acl2_proof(response)
    assert out.startswith("(defthm t")
    assert ":induct t" in out


def test_parse_hints_whole_s_expression():
    assert parse_hints_from_response('(("Goal" :induct t))') == [
        '(("Goal" :induct t))'
    ]


def test_parse_hints_strips_markdown_fence():
    resp = '```lisp\n(("Goal" :induct t))\n```'
    assert parse_hints_from_response(resp) == ['(("Goal" :induct t))']


def test_parse_hints_requires_keyword():
    assert parse_hints_from_response("((foo bar))") is None


def test_parse_hints_extracts_nested_block():
    resp = "Sure! Use this: ((Goal :expand ((foo x))))"
    assert parse_hints_from_response(resp) == [
        "((Goal :expand ((foo x))))"
    ]


def test_parse_hints_plain_text_returns_none():
    assert parse_hints_from_response("just some text") is None


def test_generate_proof_returns_stripped_and_restores_max_tokens():
    llm = FakeLLMClient(response="  " + VALID_DEFTHM + "  \n")
    out = generate_acl2_proof(llm, "my-thm", "stmt", max_tokens=4096)
    assert out == VALID_DEFTHM
    assert llm.calls[0][1] == 4096  # max_tokens set during call
    assert llm.max_tokens == 2048   # restored afterwards
    assert llm.calls[0][2] is None  # generate() called without max_tokens kwarg


def test_generate_hints_returns_parsed_hints_and_restores_max_tokens():
    llm = FakeLLMClient(response='(("Goal" :induct t))')
    out = generate_acl2_hints(llm, "stmt", "err", max_tokens=512)
    assert out == ['(("Goal" :induct t))']
    assert llm.calls[0][1] == 512
    assert llm.max_tokens == 2048


def test_generate_hints_returns_none_when_unparseable():
    llm = FakeLLMClient(response="garbage without hints")
    assert generate_acl2_hints(llm, "stmt", "err") is None


def test_generate_variants_returns_requested_count():
    llm = FakeLLMClient(response=VALID_DEFTHM)
    variants = generate_acl2_proof_variants(
        llm, "my-thm", "(implies (full st) (not (enqueue st)))",
        num_variants=3,
    )
    assert len(variants) == 3
    assert all(v.startswith("(defthm my-thm") for v in variants)
    assert llm.temperature == 0.2


def test_generate_variants_falls_back_to_skeleton_on_garbage():
    llm = FakeLLMClient(
        responses=["garbage", "(defthm my-thm\n  stmt\n  :hints ((\"Goal\" :induct t)))"]
    )
    variants = generate_acl2_proof_variants(
        llm, "my-thm", "stmt", num_variants=1
    )
    assert len(variants) == 1
    assert variants[0].startswith("(defthm my-thm")
    assert len(llm.calls) == 2


def test_generate_variants_skeleton_when_all_garbage():
    llm = FakeLLMClient(response="garbage")
    variants = generate_acl2_proof_variants(
        llm, "my-thm", "(equal 1 1)", num_variants=2
    )
    assert len(variants) == 2
    assert all(':hints (("Goal" :induct t))' in v for v in variants)
    assert all("(equal 1 1)" in v for v in variants)


def test_generate_variants_injects_diversity_tag():
    llm = FakeLLMClient(response=VALID_DEFTHM)
    generate_acl2_proof_variants(
        llm, "my-thm", "stmt", num_variants=1,
        diversity_tags=["prefer case splitting"],
    )
    assert "prefer case splitting" in llm.calls[0][0]


def test_generate_variants_repair_mode_returns_repair_first():
    response = (
        "### REPAIR\n"
        "(defthm my-thm\n  stmt\n  :hints ((\"Goal\" :induct t)))\n"
        "\n"
        "### VARIANT 1\n"
        "(defthm my-thm\n  stmt\n  :hints ((\"Goal\" :expand ((foo st)))))\n"
    )
    llm = FakeLLMClient(response=response)
    variants = generate_acl2_proof_variants(
        llm, "my-thm", "stmt", num_variants=2, repair_mode=True,
        previous_attempts=[{"script": "bad", "error": "err"}],
    )
    assert len(variants) == 2
    assert ":induct t" in variants[0]
    assert ":expand" in variants[1]


def test_generate_variants_repair_mode_ignored_without_previous_attempts():
    llm = FakeLLMClient(response=VALID_DEFTHM)
    variants = generate_acl2_proof_variants(
        llm, "my-thm", "stmt", num_variants=2, repair_mode=True,
        previous_attempts=None,
    )
    assert len(variants) == 2
    assert len(llm.calls) == 2


def test_parse_repair_variants_response_full():
    response = (
        "### REPAIR\n"
        "(defthm t\n  stmt\n  :hints ((\"Goal\" :induct t)))\n"
        "\n"
        "### VARIANT 1\n"
        "(defthm t\n  stmt\n  :hints ((\"Goal\" :expand ((foo st)))))\n"
    )
    scripts = _parse_acl2_repair_variants_response(response, "t", "stmt", 2)
    assert len(scripts) == 2
    assert ":induct t" in scripts[0]
    assert ":expand" in scripts[1]


def test_parse_repair_variants_response_missing_repair_is_filled():
    response = (
        "### VARIANT 1\n"
        "(defthm t\n  stmt\n  :hints ((\"Goal\" :expand ((foo st)))))\n"
    )
    scripts = _parse_acl2_repair_variants_response(response, "t", "stmt", 2)
    assert len(scripts) == 2
    assert scripts[0].startswith("(defthm t")
    assert ':hints (("Goal" :induct t))' in scripts[0]
    assert ":expand" in scripts[1]


def test_parse_repair_variants_response_missing_variant_is_filled():
    response = (
        "### REPAIR\n"
        "(defthm t\n  stmt\n  :hints ((\"Goal\" :induct t)))\n"
    )
    scripts = _parse_acl2_repair_variants_response(response, "t", "stmt", 2)
    assert len(scripts) == 2
    assert ":induct t" in scripts[0]
    assert scripts[1].startswith("(defthm t")
    assert ':hints (("Goal" :induct t))' in scripts[1]
