"""Unit tests for patch_ranking/ -- feature extraction and best-of-N ranking."""
from __future__ import annotations

from patch_ranking.feature_extractor import FEATURE_NAMES, extract_features, features_to_vector
from patch_ranking.patch_ranker_model import PatchRanker

GOOD_PATCH = (
    "--- a/foo.py\n+++ b/foo.py\n@@ -1,3 +1,3 @@\n-x = 1\n+x = 2\n"
)
BLOATED_PATCH = (
    "--- a/foo.py\n+++ b/foo.py\n@@ -1,10 +1,20 @@\n" + "+x = 2\n" * 15
)


def _candidate(patch_text, syntax_valid, applies_cleanly, test_result):
    return {
        "candidate_id": "x", "source": "gpt4o_run1", "patch_text": patch_text,
        "syntax_valid": syntax_valid, "applies_cleanly": applies_cleanly,
        "test_result": test_result, "rank_score": None, "rank_features": None,
    }


def test_feature_extraction_shape():
    candidate = _candidate(
        GOOD_PATCH, True, True,
        {"tests_passed": ["t1", "t2"], "tests_failed": [], "timed_out": False},
    )
    features = extract_features(candidate, fail_to_pass_tests=["t1", "t2"])
    assert set(features.keys()) == set(FEATURE_NAMES)
    vec = features_to_vector(features)
    assert vec.shape == (len(FEATURE_NAMES),)


def test_test_pass_rate_computed_correctly():
    candidate = _candidate(
        GOOD_PATCH, True, True,
        {"tests_passed": ["t1"], "tests_failed": ["t2"], "timed_out": False},
    )
    features = extract_features(candidate, fail_to_pass_tests=["t1", "t2"])
    assert features["test_pass_rate"] == 0.5
    assert features["tests_passed_count"] == 1
    assert features["tests_failed_count"] == 1


def test_invalid_syntax_scores_below_valid_passing_patch():
    ranker = PatchRanker(model_path="/nonexistent/path.pkl")  # forces fallback heuristic

    passing = _candidate(
        GOOD_PATCH, True, True,
        {"tests_passed": ["t1", "t2"], "tests_failed": [], "timed_out": False},
    )
    invalid = _candidate("not a diff", False, False, None)

    ranked = ranker.rank([passing, invalid], fail_to_pass_tests=["t1", "t2"])
    assert ranked[0]["candidate_id"] == passing["candidate_id"] or ranked[0]["rank_score"] > ranked[1]["rank_score"]
    assert ranked[0]["rank_score"] > ranked[-1]["rank_score"]


def test_fully_passing_beats_partially_passing_bloated_patch():
    ranker = PatchRanker(model_path="/nonexistent/path.pkl")

    minimal_passing = _candidate(
        GOOD_PATCH, True, True,
        {"tests_passed": ["t1", "t2"], "tests_failed": [], "timed_out": False},
    )
    bloated_partial = _candidate(
        BLOATED_PATCH, True, True,
        {"tests_passed": ["t1"], "tests_failed": ["t2"], "timed_out": False},
    )

    ranked = ranker.rank([bloated_partial, minimal_passing], fail_to_pass_tests=["t1", "t2"])
    assert ranked[0]["patch_text"] == GOOD_PATCH


def test_rank_score_is_deterministic_for_same_input():
    ranker = PatchRanker(model_path="/nonexistent/path.pkl")
    candidate = _candidate(
        GOOD_PATCH, True, True,
        {"tests_passed": ["t1"], "tests_failed": [], "timed_out": False},
    )
    score1, _ = ranker.score(candidate, ["t1"])
    score2, _ = ranker.score(candidate, ["t1"])
    assert score1 == score2
