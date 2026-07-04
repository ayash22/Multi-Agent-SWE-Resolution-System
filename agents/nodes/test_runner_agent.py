"""
Test runner agent: takes each patch candidate and executes it against the
instance's failing (+ pass-to-pass regression) tests inside an isolated
Docker container, via sandbox/docker_executor.py.

Runs once per candidate; in the LangGraph graph this node is fanned out so
all three candidates are tested in parallel (three separate containers).
"""
from __future__ import annotations

import os

from agents.state import SWEAgentState, TestResultDict
from sandbox.docker_executor import run_candidate_in_sandbox

SANDBOX_TIMEOUT_SECONDS = int(os.environ.get("SANDBOX_TIMEOUT_SECONDS", "60"))


def _sandbox_image_for(state: SWEAgentState) -> str:
    repo_slug = state["repo"].replace("/", "__")
    commit_short = state["base_commit"][:12]
    return f"swe-sandbox:{repo_slug}-{commit_short}"


def run_tests_for_candidate(state: SWEAgentState, candidate: dict) -> TestResultDict:
    if not candidate.get("applies_cleanly"):
        return TestResultDict(
            passed=False, exit_code=-1, stdout="",
            stderr="Patch does not apply cleanly; skipped test execution.",
            tests_passed=[], tests_failed=state.get("fail_to_pass_tests", []),
            timed_out=False, duration_seconds=0.0,
        )

    image = _sandbox_image_for(state)
    test_ids = state.get("fail_to_pass_tests", []) + state.get("pass_to_pass_tests", [])
    result = run_candidate_in_sandbox(
        image=image,
        patch_text=candidate["patch_text"],
        test_ids=test_ids,
        timeout_seconds=SANDBOX_TIMEOUT_SECONDS,
    )
    return TestResultDict(
        passed=result.passed,
        exit_code=result.exit_code,
        stdout=result.stdout,
        stderr=result.stderr,
        tests_passed=result.tests_passed,
        tests_failed=result.tests_failed,
        timed_out=result.timed_out,
        duration_seconds=result.duration_seconds,
    )


def _test_runner_for(candidate_id: str):
    """Factory producing a LangGraph node bound to one specific candidate_id,
    so each of the 3 parallel test-runner nodes only updates its own
    candidate's test_result rather than racing on a shared field."""

    def node(state: SWEAgentState) -> dict:
        candidates = state.get("candidates", [])
        target = next((c for c in candidates if c["candidate_id"] == candidate_id), None)
        if target is None:
            return {}
        test_result = run_tests_for_candidate(state, target)
        updated = dict(target)
        updated["test_result"] = test_result
        # Replace just this candidate in the list; other parallel branches
        # replace their own entries, and LangGraph's operator.add reducer on
        # `candidates` concatenates -- so we return only this one-item delta
        # keyed by removing the stale entry via a sentinel the merge step
        # (verifier_agent) reconciles by candidate_id, not by list identity.
        return {"candidates": [updated]}

    return node


test_runner_gpt4o_run1 = _test_runner_for("gpt4o_run1")
test_runner_gpt4o_run2 = _test_runner_for("gpt4o_run2")
test_runner_llama3 = _test_runner_for("llama3_coder")
