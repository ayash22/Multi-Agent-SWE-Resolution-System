"""
Patch ranker node: scores all N (=3) verified candidates and selects the
best one. If none pass all tests, selects the candidate that fails the
fewest tests (partial credit), and marks `resolved=False` with an honest
explanation rather than pretending a failing patch succeeded.
"""
from __future__ import annotations

from agents.state import SWEAgentState
from patch_ranking.patch_ranker_model import PatchRanker

_ranker = PatchRanker()


def select_best_candidate(state: SWEAgentState) -> dict:
    candidates = state.get("resolved_candidates", [])
    if not candidates:
        return {
            "selected_candidate": None,
            "final_patch": None,
            "resolved": False,
            "explanation": "No candidates were generated for this instance.",
            "status": "failed",
        }

    ranked = _ranker.rank(candidates, state.get("fail_to_pass_tests", []))
    best = ranked[0]
    is_valid = best.get("rank_features", {}).get("is_valid", False)

    if is_valid:
        return {
            "resolved_candidates": ranked,
            "selected_candidate": best,
            "final_patch": best["patch_text"],
            "resolved": True,
            "explanation": (
                f"Candidate '{best['source']}' passed all "
                f"{len(state.get('fail_to_pass_tests', []))} target tests "
                f"and was selected (rank_score={best['rank_score']:.3f})."
            ),
            "status": "done",
        }

    # No candidate fully passed -- decide whether to retry or return partial credit.
    retry_count = state.get("retry_count", 0)
    max_retries = state.get("max_retries", 3)
    if retry_count < max_retries:
        return {
            "resolved_candidates": ranked,
            "retry_count": retry_count + 1,
            "status": "retrying",
        }

    # Exhausted retries: return the least-bad candidate with an honest note.
    best_partial = min(
        ranked,
        key=lambda c: len((c.get("test_result") or {}).get("tests_failed", []) or ["<no result>"]),
    )
    n_failed = len((best_partial.get("test_result") or {}).get("tests_failed", []))
    n_passed = len((best_partial.get("test_result") or {}).get("tests_passed", []))
    return {
        "resolved_candidates": ranked,
        "selected_candidate": best_partial,
        "final_patch": best_partial["patch_text"],
        "resolved": False,
        "explanation": (
            f"No candidate passed all target tests after {retry_count} retries. "
            f"Returning best partial candidate '{best_partial['source']}' "
            f"({n_passed} passed / {n_failed} failed) for manual review."
        ),
        "status": "failed",
    }


def patch_ranker_node(state: SWEAgentState) -> dict:
    return select_best_candidate(state)
