"""
Shared LangGraph state for the SWE-bench resolution pipeline.

Every node reads from and writes back into this single TypedDict, which
LangGraph threads through the whole graph. Fields are additive: a node
should only set the keys it owns and leave the rest untouched (LangGraph's
default reducer for TypedDict state is "last write wins" per key, so nodes
running in parallel branches must write to *different* keys -- see the
`candidates` list design below, where each parallel coder node appends its
own entry rather than all writing to one shared field).
"""
from __future__ import annotations

import operator
from typing import Annotated, Any, Literal, TypedDict


class PlanDict(TypedDict):
    issue_summary: str
    likely_files: list[str]
    fix_strategy: str
    test_hints: str


class RetrievedChunkDict(TypedDict):
    file_path: str
    chunk_type: str
    name: str
    class_name: str | None
    start_line: int
    end_line: int
    code: str
    imports_used: list[str]
    docstring: str | None
    retrieval_score: float
    retrieval_reason: str


class TestResultDict(TypedDict):
    passed: bool
    exit_code: int
    stdout: str
    stderr: str
    tests_passed: list[str]
    tests_failed: list[str]
    timed_out: bool
    duration_seconds: float


class PatchCandidateDict(TypedDict):
    candidate_id: str
    source: Literal["gpt4o_run1", "gpt4o_run2", "llama3_finetuned"]
    patch_text: str
    syntax_valid: bool
    applies_cleanly: bool
    test_result: TestResultDict | None
    rank_score: float | None
    rank_features: dict[str, Any] | None


class SWEAgentState(TypedDict, total=False):
    # ---- instance input ----
    instance_id: str
    repo: str
    base_commit: str
    issue_text: str
    failing_test_file: str
    fail_to_pass_tests: list[str]
    pass_to_pass_tests: list[str]
    repo_local_path: str

    # ---- planner output ----
    plan: PlanDict

    # ---- retrieval output ----
    retrieved_chunks: list[RetrievedChunkDict]

    # ---- coder outputs: each parallel branch appends here.
    # Annotated with operator.add so LangGraph concatenates the single-item
    # lists returned by each parallel coder/test-runner node instead of one
    # branch clobbering another's write. ----
    candidates: Annotated[list[PatchCandidateDict], operator.add]

    # ---- verifier output: `candidates` above accumulates additively across
    # parallel branches (coder writes + test_runner writes), so it may hold
    # duplicate per-candidate entries. The verifier reconciles those into one
    # canonical entry per candidate_id and writes the clean list here, in a
    # plain (last-write-wins) field so it isn't subject to the same additive
    # reducer -- downstream nodes (patch_ranker, graph routing) read from
    # `resolved_candidates`, not `candidates`. ----
    resolved_candidates: list[PatchCandidateDict]

    # ---- ranking / selection ----
    selected_candidate: PatchCandidateDict | None
    all_candidates_failed: bool

    # ---- control flow ----
    retry_count: int
    max_retries: int
    status: Literal[
        "pending", "planning", "retrieving", "coding", "testing",
        "verifying", "ranking", "retrying", "done", "failed"
    ]
    error_log: Annotated[list[str], operator.add]

    # ---- final output ----
    final_patch: str | None
    resolved: bool | None
    explanation: str | None
