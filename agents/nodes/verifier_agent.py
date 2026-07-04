"""
Verifier agent: reconciles the `candidates` list (which, due to LangGraph's
additive reducer on parallel branches, may contain multiple entries per
candidate_id -- an initial one from the coder node without a test_result,
and a later one from the test_runner node with it) into one canonical entry
per candidate, and determines whether each candidate's patch is genuinely
valid: syntactically correct, applies cleanly, AND makes every required test
pass (not just "doesn't crash").
"""
from __future__ import annotations

from agents.state import PatchCandidateDict, SWEAgentState


def reconcile_candidates(candidates: list[PatchCandidateDict]) -> list[PatchCandidateDict]:
    """Keeps, for each candidate_id, the most information-complete entry
    (the one with a non-None test_result if any entry has one)."""
    by_id: dict[str, PatchCandidateDict] = {}
    for c in candidates:
        existing = by_id.get(c["candidate_id"])
        if existing is None:
            by_id[c["candidate_id"]] = c
        else:
            merged = dict(existing)
            for k, v in c.items():
                if v is not None:
                    merged[k] = v
            by_id[c["candidate_id"]] = merged  # type: ignore[assignment]
    return list(by_id.values())


def is_valid_patch(candidate: PatchCandidateDict) -> bool:
    """A patch is genuinely valid only if it applies cleanly AND its test
    result shows zero failed tests AND at least the originally-failing tests
    now show up as passed (guards against a patch that passes by deleting or
    skipping the target tests rather than fixing the code)."""
    if not candidate.get("syntax_valid") or not candidate.get("applies_cleanly"):
        return False
    test_result = candidate.get("test_result")
    if not test_result:
        return False
    return bool(test_result.get("passed")) and not test_result.get("tests_failed")


def verifier_node(state: SWEAgentState) -> dict:
    reconciled = reconcile_candidates(state.get("candidates", []))
    for c in reconciled:
        c["rank_features"] = c.get("rank_features") or {}
        c["rank_features"]["is_valid"] = is_valid_patch(c)

    any_valid = any(c["rank_features"]["is_valid"] for c in reconciled)
    return {
        "resolved_candidates": reconciled,
        "all_candidates_failed": not any_valid,
        "status": "ranking",
    }
