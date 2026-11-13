# tests/unit/test_mcts.py
#
# MCTS traversal (UCB1 selection + backpropagation) + --search flag.

import math

from isir.cli.verify import _setup_arg_parser
from isir.verification.perf.perf_scorer import PERFNode
from isir.verification.perf.mcts_traversal import MCTSConfig, MCTSTraversal


class TestSearchFlag:
    def test_search_flag_parsed(self):
        args = _setup_arg_parser().parse_args(["x.isir", "--search", "mcts"])
        assert args.search == "mcts"
        args = _setup_arg_parser().parse_args(["x.isir", "--search", "perf"])
        assert args.search == "perf"


class TestUcb:
    def _mk(self):
        # Build a traversal instance without running the full setup.
        t = MCTSTraversal.__new__(MCTSTraversal)
        t.config = type("C", (), {"primary_dimension": "subgoal_reduction"})()
        t.mcts = MCTSConfig()
        return t

    def test_unvisited_child_has_infinite_ucb(self):
        t = self._mk()
        parent = PERFNode(script="p")
        child = PERFNode(script="c", parent=parent)
        visits = {id(parent): 5, id(child): 0}
        values = {id(parent): 0.5, id(child): 0.0}
        assert t._ucb(child, parent, visits, values) == math.inf

    def test_ucb_balances_exploration(self):
        t = self._mk()
        parent = PERFNode(script="p")
        a = PERFNode(script="a", parent=parent)
        b = PERFNode(script="b", parent=parent)
        visits = {id(parent): 10, id(a): 5, id(b): 1}
        values = {id(parent): 0.5, id(a): 0.6, id(b): 0.4}
        # b has fewer visits -> larger exploration bonus; a has higher Q.
        ua = t._ucb(a, parent, visits, values)
        ub = t._ucb(b, parent, visits, values)
        assert ua > 0.0 and ub > 0.0

    def test_cheap_reward(self):
        t = self._mk()
        ok = PERFNode(script="ok")
        ok.verification_result = {"success": True}
        assert t._cheap_reward(ok) == 1.0
        bad = PERFNode(script="bad")
        bad.verification_result = {"success": False, "error": "Error: x Error: y"}
        # 2 errors -> 1/3
        assert abs(t._cheap_reward(bad) - 1.0 / 3.0) < 1e-9

    def test_select_descends_to_leaf(self):
        t = self._mk()
        root = PERFNode(script="root")
        child = PERFNode(script="child", parent=root)
        root.children = [child]
        visits = {id(root): 2, id(child): 1}
        values = {id(root): 0.5, id(child): 0.7}
        node, path = t._select(root, visits, values)
        assert node is child
        assert path == [root, child]

    def test_select_prefers_higher_value_visited_child(self):
        # With the children-value fix, UCB's exploitation term (Q) must be
        # non-zero, so a higher-score visited child is selected over a lower one.
        t = self._mk()
        root = PERFNode(script="root")
        high = PERFNode(script="high", parent=root)
        low = PERFNode(script="low", parent=root)
        root.children = [high, low]
        visits = {id(root): 3, id(high): 1, id(low): 1}
        values = {id(root): 0.5, id(high): 0.9, id(low): 0.1}
        node, _ = t._select(root, visits, values)
        assert node is high

    def test_select_prefers_unvisited_over_visited(self):
        t = self._mk()
        root = PERFNode(script="root")
        visited = PERFNode(script="visited", parent=root)
        unvisited = PERFNode(script="unvisited", parent=root)
        root.children = [visited, unvisited]
        visits = {id(root): 3, id(visited): 2, id(unvisited): 0}
        values = {id(root): 0.5, id(visited): 0.9, id(unvisited): 0.0}
        node, _ = t._select(root, visits, values)
        assert node is unvisited


class TestMCTSFullTraverse:
    def _make_traversal(self):
        from isir.verification.perf.mcts_traversal import MCTSConfig, MCTSTraversal
        t = MCTSTraversal.__new__(MCTSTraversal)
        t.mcts = MCTSConfig(c=1.414, iterations=10, branches_per_node=2)
        t.config = type("C", (), {"always_verify_children": False})()
        t.stats = _FakeStats()
        t.obligation = {"property": "p"}
        t.best_candidate_script = None
        t.best_candidate_score = -1.0
        t._finished = []
        return t

    def test_traverse_finds_successful_child(self):
        t = self._make_traversal()

        # root
        root = PERFNode(script="root")
        t._prepare = lambda: root

        child_gen = {"root": ["a", "b"], "a": ["c", "d"]}
        successes = {"c"}  # the "proof" is at node c

        def gen(frontier, depth):
            out = []
            for n in frontier:
                for name in child_gen.get(n.script, []):
                    out.append(PERFNode(script=name, parent=n, depth=depth))
            return out

        def verify(children):
            for c in children:
                c.verification_result = {"success": c.script in successes,
                                         "error": "" if c.script in successes else "Error: nope"}
            return children

        def repair(children, depth):
            return children

        def evaluate(node):
            return node.verification_result

        t._generate_children = gen
        t._verify_children = verify
        t._repair_children = repair
        t._filter_children = lambda ch: ch
        t._evaluate_node = evaluate
        t._record_successful_proof = lambda p, s: t._finished.append((p, s))
        t._finish_success = lambda n: t._finished.append(("found", n.script))

        script, stats = t.traverse()
        assert script == "c", f"expected 'c', got {script!r}"
        assert t._finished and t._finished[-1][0] == "found"

    def test_traverse_terminates_without_proof(self):
        t = self._make_traversal()
        root = PERFNode(script="root")
        t._prepare = lambda: root
        t._generate_children = lambda frontier, depth: [
            PERFNode(script=f"x{i}", parent=frontier[0], depth=depth) for i in range(2)
        ]
        t._verify_children = lambda ch: [setattr(c, "verification_result", {"success": False, "error": "Error: bad"}) or c for c in ch]
        t._repair_children = lambda ch, d: ch
        t._filter_children = lambda ch: ch
        t._evaluate_node = lambda n: n.verification_result
        t._record_successful_proof = lambda p, s: None
        t._finish_success = lambda n: None

        script, stats = t.traverse()
        assert script is None  # no proof found, but terminates cleanly


class _FakeStats:
    def __init__(self):
        self.recorded = 0
    def record_verifier_call(self):
        self.recorded += 1
    def record_success(self, depth):
        pass
    def finish(self):
        pass
