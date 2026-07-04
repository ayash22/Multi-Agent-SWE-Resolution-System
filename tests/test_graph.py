"""Unit tests for agents/graph.py -- verifies the LangGraph state machine
compiles with the expected nodes and parallel fan-out/fan-in structure,
without requiring any OpenAI/Docker/GPU calls."""
from __future__ import annotations

from agents.graph import build_graph, route_after_ranking


def test_graph_compiles():
    app = build_graph()
    assert app is not None


def test_graph_contains_all_expected_nodes():
    app = build_graph()
    nodes = set(app.get_graph().nodes.keys())
    expected = {
        "__start__", "__end__", "planner", "retrieval", "retry_dispatch",
        "coder_gpt4o_run1", "coder_gpt4o_run2", "llama_coder",
        "test_runner_run1", "test_runner_run2", "test_runner_llama",
        "verifier", "patch_ranker",
    }
    assert expected.issubset(nodes)


def test_coder_branches_fan_out_from_retrieval_and_retry_dispatch():
    app = build_graph()
    edges = app.get_graph().edges
    sources_to_coder_run1 = {e.source for e in edges if e.target == "coder_gpt4o_run1"}
    assert "retrieval" in sources_to_coder_run1
    assert "retry_dispatch" in sources_to_coder_run1


def test_verifier_has_three_incoming_test_runner_edges():
    app = build_graph()
    edges = app.get_graph().edges
    sources_to_verifier = {e.source for e in edges if e.target == "verifier"}
    assert sources_to_verifier == {"test_runner_run1", "test_runner_run2", "test_runner_llama"}


def test_route_after_ranking_retry():
    assert route_after_ranking({"status": "retrying"}) == "retry"


def test_route_after_ranking_end():
    assert route_after_ranking({"status": "done"}) == "end"
    assert route_after_ranking({"status": "failed"}) == "end"


def test_run_instance_passes_a_bounded_recursion_limit(monkeypatch):
    """Regression/guardrail test: run_instance must always invoke the graph
    with an explicit, finite recursion_limit -- this is the hard,
    LangGraph-level ceiling that protects against any future bug in our own
    retry-counting logic causing an unbounded loop."""
    import agents.graph as graph_module

    captured = {}

    class FakeApp:
        def invoke(self, state, config=None):
            captured["config"] = config
            return {**state, "status": "done", "resolved": True, "final_patch": "diff"}

    monkeypatch.setattr(graph_module, "build_graph", lambda: FakeApp())

    graph_module.run_instance({
        "instance_id": "x", "repo": "a/b", "base_commit": "c",
        "issue_text": "text", "repo_local_path": "/tmp/x",
    })

    assert captured["config"] is not None
    assert isinstance(captured["config"].get("recursion_limit"), int)
    assert 0 < captured["config"]["recursion_limit"] < 1000  # finite and sane


def test_run_instance_handles_recursion_limit_gracefully(monkeypatch):
    """If the hard recursion ceiling is ever hit, run_instance must return a
    clean failed state rather than letting GraphRecursionError propagate as
    an unhandled exception."""
    from langgraph.errors import GraphRecursionError

    import agents.graph as graph_module

    class FakeApp:
        def invoke(self, state, config=None):
            raise GraphRecursionError("simulated recursion limit hit")

    monkeypatch.setattr(graph_module, "build_graph", lambda: FakeApp())

    result = graph_module.run_instance({
        "instance_id": "x", "repo": "a/b", "base_commit": "c",
        "issue_text": "text", "repo_local_path": "/tmp/x",
    })

    assert result["resolved"] is False
    assert result["status"] == "failed"
    assert "recursion" in result["explanation"].lower()
