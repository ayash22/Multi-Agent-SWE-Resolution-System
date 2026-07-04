"""
LangGraph orchestration wiring all agent nodes together:

    issue_input -> planner -> retrieval_agent
        -> [PARALLEL] coder_gpt4o_run1, coder_gpt4o_run2, llama_coder
        -> [PARALLEL] test_runner (x3, one per candidate)
        -> verifier
        -> patch_ranker
        -> [CONDITIONAL]
             - best candidate passes tests            -> END (resolved)
             - no candidate passes, retry_count < max  -> back to coder stage
             - retries exhausted                       -> END (partial credit)

The three coder nodes and three test-runner nodes are genuinely fanned out
as parallel LangGraph edges (not a Python for-loop), so LangGraph executes
them concurrently and fans them back in automatically once all three
branches complete, using the `operator.add` reducer on `state["candidates"]`
(see agents/state.py) to merge their independent writes.
"""
from __future__ import annotations

from langgraph.graph import END, StateGraph

from agents.nodes.coder_agent import coder_node_run1, coder_node_run2
from agents.nodes.llama_coder_agent import llama_coder_node
from agents.nodes.patch_ranker import patch_ranker_node
from agents.nodes.planner_agent import planner_node
from agents.nodes.retrieval_agent import retrieval_node
from agents.nodes.test_runner_agent import (
    test_runner_gpt4o_run1,
    test_runner_gpt4o_run2,
    test_runner_llama3,
)
from agents.nodes.verifier_agent import verifier_node
from agents.state import SWEAgentState


def route_after_ranking(state: SWEAgentState) -> str:
    if state.get("status") == "retrying":
        return "retry"
    return "end"


def _retry_dispatch(state: SWEAgentState) -> dict:
    """Pass-through node: exists purely so `add_conditional_edges` has a
    single named destination for the 'retry' branch, from which we can fan
    out to all three coder nodes in true parallel (mirroring the initial
    fan-out from `retrieval`)."""
    return {"status": "coding"}


def build_graph():
    """Builds the compiled LangGraph state machine. Retries are routed
    through a small `retry_dispatch` pass-through node so that, on retry,
    all three coder branches genuinely re-run in parallel (mirroring the
    initial fan-out from `retrieval`) rather than serially -- LangGraph's
    `add_conditional_edges` maps one condition value to exactly one
    destination node, so the dispatch node gives the retry path a single
    named target to fan out from."""
    graph = StateGraph(SWEAgentState)

    graph.add_node("planner", planner_node)
    graph.add_node("retrieval", retrieval_node)
    graph.add_node("retry_dispatch", _retry_dispatch)

    graph.add_node("coder_gpt4o_run1", coder_node_run1)
    graph.add_node("coder_gpt4o_run2", coder_node_run2)
    graph.add_node("llama_coder", llama_coder_node)

    graph.add_node("test_runner_run1", test_runner_gpt4o_run1)
    graph.add_node("test_runner_run2", test_runner_gpt4o_run2)
    graph.add_node("test_runner_llama", test_runner_llama3)

    graph.add_node("verifier", verifier_node)
    graph.add_node("patch_ranker", patch_ranker_node)

    graph.set_entry_point("planner")
    graph.add_edge("planner", "retrieval")

    for source in ("retrieval", "retry_dispatch"):
        graph.add_edge(source, "coder_gpt4o_run1")
        graph.add_edge(source, "coder_gpt4o_run2")
        graph.add_edge(source, "llama_coder")

    graph.add_edge("coder_gpt4o_run1", "test_runner_run1")
    graph.add_edge("coder_gpt4o_run2", "test_runner_run2")
    graph.add_edge("llama_coder", "test_runner_llama")

    graph.add_edge("test_runner_run1", "verifier")
    graph.add_edge("test_runner_run2", "verifier")
    graph.add_edge("test_runner_llama", "verifier")

    graph.add_edge("verifier", "patch_ranker")

    graph.add_conditional_edges(
        "patch_ranker",
        route_after_ranking,
        {"retry": "retry_dispatch", "end": END},
    )

    return graph.compile()


def run_instance(initial_state: dict) -> dict:
    """Runs the full pipeline for one SWE-bench instance and returns the
    final state, including `final_patch`, `resolved`, and `explanation`."""
    app = build_graph()
    default_state = {
        "candidates": [],
        "resolved_candidates": [],
        "retry_count": 0,
        "max_retries": 3,
        "status": "pending",
        "error_log": [],
    }
    state = {**default_state, **initial_state}
    return app.invoke(state)


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser()
    parser.add_argument("instance_jsonl_line", help="Path to a file containing one SWE-bench instance as JSON")
    args = parser.parse_args()

    with open(args.instance_jsonl_line) as f:
        instance = json.load(f)

    final_state = run_instance({
        "instance_id": instance["instance_id"],
        "repo": instance["repo"],
        "base_commit": instance["base_commit"],
        "issue_text": instance["problem_statement"],
        "failing_test_file": instance.get("failing_test_file", ""),
        "fail_to_pass_tests": json.loads(instance.get("FAIL_TO_PASS", "[]")),
        "pass_to_pass_tests": json.loads(instance.get("PASS_TO_PASS", "[]")),
        "repo_local_path": instance["repo_local_path"],
    })
    print(json.dumps({
        "resolved": final_state.get("resolved"),
        "explanation": final_state.get("explanation"),
    }, indent=2))
