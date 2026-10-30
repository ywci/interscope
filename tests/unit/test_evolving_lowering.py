# tests/unit/test_evolving_lowering.py
#
# Phase 1 lowering: confirmed_projection (Section 4) + the ast->evolving
# preservation pass (Candidate/OneOf bridging).

from isir.dialects.evolving_spec import EvolvingItem, EvolvingSpec
from isir.dialects.isir import SpecModule
from isir.lowering.evolving import ConfirmedSpec, ast_to_evolving, confirmed_projection
from isir.parser.ast import Candidate, Function, Module, OneOf, Rule, State


def _spec_module(functions):
    return SpecModule(name="fifo", state_ops=[], rule_ops=[], inputs=[], outputs=[],
                      functions=functions, property_ops=[], proof_obligations=[])


class TestConfirmedProjection:
    def test_splits_lowered_vs_deferred(self):
        spec = _spec_module([
            {"name": "sigmoid", "params": [], "return": "bits<8>"},  # bodyless
            {"name": "sel", "params": [], "return": "bits<8>"},      # bodyless
            {"name": "inc", "params": [], "return": "bits<8>", "body": "(add v 1)"},
        ])
        evolving = EvolvingSpec("fifo", items=[
            EvolvingItem("sigmoid", defer_verification=True),
        ])
        c = confirmed_projection(evolving, spec)
        assert c.lowered_placeholders == ["sel"]
        assert c.deferred_placeholders == ["sigmoid"]

    def test_no_defer_flags_all_lowered(self):
        spec = _spec_module([{"name": "sigmoid", "params": [], "return": "bits<8>"}])
        c = confirmed_projection(EvolvingSpec("fifo"), spec)
        assert c.lowered_placeholders == ["sigmoid"]
        assert c.deferred_placeholders == []


class TestAstToEvolving:
    def test_candidate_and_oneof_bridged(self):
        m = Module(
            name="fifo",
            rules=[
                Rule(name="rule_write",
                     condition=Candidate(value="(lt (read count) 8)", confidence=0.9,
                                         source="ignore writes when full",
                                         alternatives=[{"value": "(not (read full))", "confidence": 0.8}]),
                     action=[OneOf(alternatives=["(write count (add (read count) 1))",
                                                 "(write count (read count))"])]),
            ],
        )
        ev = ast_to_evolving(m)
        item = ev.item("rule_write")
        assert item is not None
        assert item.provenance == "ignore writes when full"
        assert len(item.alternatives) == 3  # 1 candidate alt + 2 one_of alts
        assert item.partial_spec == {"unresolved": True}  # the unresolved OneOf

    def test_bodyless_function_becomes_partial_spec(self):
        m = Module(name="bb", functions=[Function(name="sigmoid", params=[], return_type="bits<8>")])
        ev = ast_to_evolving(m)
        item = ev.item("sigmoid")
        assert item is not None
        assert item.partial_spec == {"unresolved": True}

    def test_plain_module_produces_no_items(self):
        m = Module(name="plain", rules=[Rule(name="tick", condition="true", action=["(write r 1)"])])
        ev = ast_to_evolving(m)
        assert ev.items == []
