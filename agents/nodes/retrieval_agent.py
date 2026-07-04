"""
Retrieval agent: given the issue + plan, builds/loads the code index for the
target repo and runs hybrid retrieval to gather the code context the coder
agents will condition on.
"""
from __future__ import annotations

import os

from agents.state import SWEAgentState
from retrieval.code_indexer import build_index
from retrieval.code_retriever import retrieve_context

INDEX_CACHE_ROOT = os.environ.get("INDEX_CACHE_ROOT", ".index_cache")


def retrieve_for_instance(state: SWEAgentState, top_k: int = 10) -> list[dict]:
    repo_local_path = state["repo_local_path"]
    cache_dir = os.path.join(
        INDEX_CACHE_ROOT,
        f"{state['repo'].replace('/', '__')}_{state['base_commit'][:12]}",
    )
    index = build_index(repo_local_path, cache_dir=cache_dir)

    plan = state.get("plan", {})
    hits = retrieve_context(
        index,
        issue_text=state["issue_text"],
        fix_strategy=plan.get("fix_strategy", ""),
        failing_test_file=state.get("failing_test_file", ""),
        top_k=top_k,
    )
    return [h.to_dict() for h in hits]


def retrieval_node(state: SWEAgentState) -> dict:
    """LangGraph node entrypoint: reads `issue_text`, `plan`, `repo_local_path`,
    `failing_test_file` from state, writes `retrieved_chunks` and `status`."""
    chunks = retrieve_for_instance(state)
    return {"retrieved_chunks": chunks, "status": "coding"}
