"""Unit tests for agents/nodes/verifier_agent.py -- reconciling the
additive-reducer candidate list (coder writes + test_runner writes,
potentially across multiple retries) into one canonical entry per
candidate_id, and correctly judging patch validity."""
from __future__ import annotations

from agents.nodes.verifier_agent import is_valid_patch, reconcile_candidates


def _coder_write(cid, patch_text="patch-v1"):
    return {
        "candidate_id": cid, "source": "gpt4o_run1", "patch_text": patch_text,
        "syntax_valid": True, "applies_cleanly": True,
        "test_result": None, "rank_score": None, "rank_features": None,
    }


def _test_runner_write(cid, patch_text, test_result):
    return {
        "candidate_id": cid, "source": "gpt4o_run1", "patch_text": patch_text,
        "syntax_valid": True, "applies_cleanly": True,
        "test_result": test_result, "rank_score": None, "rank_features": None,
    }


def test_reconcile_merges_coder_and_test_runner_writes():
    test_result = {"passed": True, "tests_passed": ["t1"], "tests_failed": []}
    candidates = [
        _coder_write("a"),
        _test_runner_write("a", "patch-v1", test_result),
    ]
    reconciled = reconcile_candidates(candidates)
    assert len(reconciled) == 1
    assert reconciled[0]["test_result"] == test_result


def test_reconcile_keeps_multiple_distinct_candidates_separate():
    candidates = [
        _coder_write("a"),
        _coder_write("b"),
        _test_runner_write("a", "patch-v1", {"passed": True, "tests_passed": [], "tests_failed": []}),
        _test_runner_write("b", "patch-v1", {"passed": False, "tests_passed": [], "tests_failed": ["t1"]}),
    ]
    reconciled = reconcile_candidates(candidates)
    assert {c["candidate_id"] for c in reconciled} == {"a", "b"}


def test_reconcile_after_retry_reflects_latest_patch_not_stale_test_result():
    """Regression test: after a retry, a candidate_id gets a fresh coder
    write (new patch_text, test_result=None) followed by a fresh
    test_runner write. The reconciled record must end up reflecting the
    NEW patch + NEW test result, not a stale test_result from before the
    retry leaking onto the new patch."""
    old_test_result = {"passed": False, "tests_passed": [], "tests_failed": ["t1"]}
    new_test_result = {"passed": True, "tests_passed": ["t1"], "tests_failed": []}

    candidates = [
        _coder_write("a", "patch-v1"),
        _test_runner_write("a", "patch-v1", old_test_result),
        _coder_write("a", "patch-v2"),  # retry produced a new patch
        _test_runner_write("a", "patch-v2", new_test_result),
    ]
    reconciled = reconcile_candidates(candidates)
    assert len(reconciled) == 1
    assert reconciled[0]["patch_text"] == "patch-v2"
    assert reconciled[0]["test_result"] == new_test_result


def test_is_valid_patch_requires_all_conditions():
    valid = {
        "syntax_valid": True, "applies_cleanly": True,
        "test_result": {"passed": True, "tests_failed": []},
    }
    assert is_valid_patch(valid) is True

    invalid_syntax = {**valid, "syntax_valid": False}
    assert is_valid_patch(invalid_syntax) is False

    no_test_result = {**valid, "test_result": None}
    assert is_valid_patch(no_test_result) is False

    has_failures = {
        "syntax_valid": True, "applies_cleanly": True,
        "test_result": {"passed": False, "tests_failed": ["t1"]},
    }
    assert is_valid_patch(has_failures) is False


def test_is_valid_patch_rejects_gamed_test_removal():
    """A patch that 'passes' by having zero tests actually run (e.g. it
    deleted/skipped the target tests) must not be treated as valid just
    because tests_failed is empty -- `passed` must also be True."""
    gamed = {
        "syntax_valid": True, "applies_cleanly": True,
        "test_result": {"passed": False, "tests_failed": []},
    }
    assert is_valid_patch(gamed) is False
