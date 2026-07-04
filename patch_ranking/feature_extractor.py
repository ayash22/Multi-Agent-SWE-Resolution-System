"""
Extracts a fixed-size feature vector from a (issue, patch_candidate) pair for
the patch ranker model to score. Every feature here is cheap to compute
(no LLM calls) since it runs once per candidate per instance at ranking time.
"""
from __future__ import annotations

import ast

import numpy as np

FEATURE_NAMES = [
    "syntax_valid",
    "applies_cleanly",
    "tests_passed_count",
    "tests_failed_count",
    "test_pass_rate",
    "patch_size_lines",
    "patch_num_files",
    "patch_num_hunks",
    "timed_out",
    "code_complexity_delta",
]


def _patch_stats(patch_text: str) -> dict:
    lines = patch_text.splitlines()
    changed = sum(
        1 for line in lines
        if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))
    )
    files = {line[6:] for line in lines if line.startswith("--- a/")}
    hunks = sum(1 for line in lines if line.startswith("@@"))
    return {"size": changed, "num_files": len(files), "num_hunks": hunks}


def _cyclomatic_complexity(source: str) -> int:
    """Rough cyclomatic complexity proxy: counts branching AST nodes. Used
    only as a relative signal between candidates' added/removed code, not an
    absolute code-quality judgment."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return 0
    branch_types = (ast.If, ast.For, ast.While, ast.Try, ast.ExceptHandler, ast.BoolOp)
    return sum(1 for n in ast.walk(tree) if isinstance(n, branch_types))


def _complexity_delta(patch_text: str) -> float:
    """Approximates the change in cyclomatic complexity by parsing the
    added-lines-only and removed-lines-only pseudo-snippets. This is
    intentionally crude (added/removed lines alone aren't valid standalone
    Python in general) -- we wrap in a dummy function and best-effort parse,
    falling back to 0 on failure, since it's used as one weak signal among
    many rather than a ground truth."""
    added = "\n".join(
        line[1:] for line in patch_text.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    )
    removed = "\n".join(
        line[1:] for line in patch_text.splitlines()
        if line.startswith("-") and not line.startswith("---")
    )

    def safe_complexity(snippet: str) -> int:
        wrapped = "def _f():\n" + "\n".join(
            f"    {line}" if line.strip() else "" for line in snippet.splitlines()
        )
        return _cyclomatic_complexity(wrapped)

    return float(safe_complexity(added) - safe_complexity(removed))


def extract_features(candidate: dict, fail_to_pass_tests: list[str]) -> dict:
    """`candidate` follows the PatchCandidateDict shape (patch_text,
    syntax_valid, applies_cleanly, test_result)."""
    patch_text = candidate.get("patch_text", "") or ""
    stats = _patch_stats(patch_text)
    test_result = candidate.get("test_result") or {}

    n_passed = len(test_result.get("tests_passed", []))
    n_failed = len(test_result.get("tests_failed", []))
    total = n_passed + n_failed
    pass_rate = (n_passed / total) if total else 0.0

    return {
        "syntax_valid": float(bool(candidate.get("syntax_valid"))),
        "applies_cleanly": float(bool(candidate.get("applies_cleanly"))),
        "tests_passed_count": float(n_passed),
        "tests_failed_count": float(n_failed),
        "test_pass_rate": pass_rate,
        "patch_size_lines": float(stats["size"]),
        "patch_num_files": float(stats["num_files"]),
        "patch_num_hunks": float(stats["num_hunks"]),
        "timed_out": float(bool(test_result.get("timed_out"))),
        "code_complexity_delta": _complexity_delta(patch_text),
    }


def features_to_vector(features: dict) -> np.ndarray:
    return np.array([features[name] for name in FEATURE_NAMES], dtype="float32")
