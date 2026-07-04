"""Unit tests for sandbox/docker_executor.py's pure helper functions
(pytest output parsing, tar packaging) that don't require a live Docker
daemon. Full container execution is integration-tested separately (requires
Docker -- see tests/test_docker_sandbox_integration.py)."""
from __future__ import annotations

import tarfile

from sandbox.docker_executor import _make_tar, _parse_pytest_output


def test_parse_pytest_output_extracts_passed_and_failed():
    stdout = (
        "tests/test_foo.py::test_a PASSED\n"
        "tests/test_foo.py::test_b FAILED\n"
        "tests/test_foo.py::test_c PASSED\n"
    )
    passed, failed = _parse_pytest_output(stdout)
    assert passed == ["tests/test_foo.py::test_a", "tests/test_foo.py::test_c"]
    assert failed == ["tests/test_foo.py::test_b"]


def test_parse_pytest_output_handles_no_tests():
    passed, failed = _parse_pytest_output("no tests ran")
    assert passed == []
    assert failed == []


def test_make_tar_produces_valid_tar_with_correct_content():
    content = b"--- a/foo.py\n+++ b/foo.py\n"
    stream = _make_tar("agent_patch.diff", content)

    with tarfile.open(fileobj=stream, mode="r") as tar:
        names = tar.getnames()
        assert names == ["agent_patch.diff"]
        extracted = tar.extractfile("agent_patch.diff").read()
        assert extracted == content
