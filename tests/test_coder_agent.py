"""Unit tests for agents/nodes/coder_agent.py -- diff extraction and
syntax/apply validation, independent of any real GPT-4o call."""
from __future__ import annotations

import subprocess

import pytest

from agents.nodes.coder_agent import (
    check_applies_cleanly,
    extract_diff,
    validate_syntax,
)

VALID_DIFF = (
    "--- a/foo.py\n+++ b/foo.py\n@@ -1,1 +1,1 @@\n-x = 1\n+x = 2\n"
)


def test_extract_diff_from_fenced_response():
    raw = f"Here is the fix:\n```diff\n{VALID_DIFF}```\n"
    assert extract_diff(raw).strip() == VALID_DIFF.strip()


def test_extract_diff_from_unfenced_response():
    raw = VALID_DIFF
    assert extract_diff(raw).strip() == VALID_DIFF.strip()


def test_extract_diff_raises_on_no_diff_found():
    with pytest.raises(ValueError):
        extract_diff("I cannot produce a patch for this issue.")


def test_validate_syntax_accepts_well_formed_diff():
    assert validate_syntax(VALID_DIFF) is True


def test_validate_syntax_rejects_missing_hunk():
    assert validate_syntax("--- a/foo.py\n+++ b/foo.py\n") is False


def test_validate_syntax_rejects_prose():
    assert validate_syntax("This is not a diff at all.") is False


def test_is_implausibly_large_flags_oversized_patch():
    from agents.nodes.coder_agent import is_implausibly_large
    huge_diff = "--- a/foo.py\n+++ b/foo.py\n@@ -1,400 +1,400 @@\n" + "+x = 1\n" * 350
    assert is_implausibly_large(huge_diff) is True


def test_is_implausibly_large_accepts_minimal_patch():
    from agents.nodes.coder_agent import is_implausibly_large
    assert is_implausibly_large(VALID_DIFF) is False


def test_count_changed_lines():
    from agents.nodes.coder_agent import count_changed_lines
    assert count_changed_lines(VALID_DIFF) == 2  # one - line, one + line


def test_check_applies_cleanly_against_real_repo(tmp_path):
    """Builds a tiny real git repo, confirms a correct patch applies cleanly
    and a patch against nonexistent content does not."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
    (repo / "foo.py").write_text("x = 1\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=repo, check=True)

    assert check_applies_cleanly(VALID_DIFF, str(repo)) is True

    bad_diff = "--- a/foo.py\n+++ b/foo.py\n@@ -1,1 +1,1 @@\n-y = 99\n+y = 100\n"
    assert check_applies_cleanly(bad_diff, str(repo)) is False
