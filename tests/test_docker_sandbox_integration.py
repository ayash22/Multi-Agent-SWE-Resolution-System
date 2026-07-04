"""
Integration test for sandbox/docker_executor.py against a REAL Docker
daemon. This is intentionally separate from tests/test_docker_sandbox_helpers.py
(which only tests pure functions) because it actually builds an image,
launches a container, applies a patch, and runs pytest inside it end to end.

Auto-skips with a clear reason if:
  - the `docker` package can't connect to a daemon (no Docker available), or
  - `swe-sandbox-test:latest` hasn't been built yet (see the docstring below).

This test does NOT fabricate a pass: if Docker isn't available in your
environment, it is honestly reported as SKIPPED, not silently omitted.

To actually run this test:
    docker build -t swe-sandbox-test:latest -f tests/fixtures/Dockerfile.test-sandbox tests/fixtures
    pytest tests/test_docker_sandbox_integration.py -v
"""
from __future__ import annotations

import pytest

from sandbox.docker_executor import DockerSandbox

TEST_IMAGE = "swe-sandbox-test:latest"


def _docker_available() -> bool:
    try:
        import docker
        client = docker.from_env()
        client.ping()
        return True
    except Exception:
        return False


def _test_image_available() -> bool:
    try:
        import docker
        client = docker.from_env()
        client.images.get(TEST_IMAGE)
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _docker_available(),
    reason="No Docker daemon reachable from this environment -- this is an "
           "integration test, skipped honestly rather than faked.",
)


@pytest.mark.skipif(
    not _test_image_available(),
    reason=f"Test image '{TEST_IMAGE}' not built. Run: docker build -t {TEST_IMAGE} "
           "-f tests/fixtures/Dockerfile.test-sandbox tests/fixtures",
)
def test_sandbox_applies_patch_and_runs_passing_test():
    sandbox = DockerSandbox(image=TEST_IMAGE, timeout_seconds=30)
    patch = (
        "--- a/calc.py\n+++ b/calc.py\n@@ -1,2 +1,2 @@\n"
        "def add(a, b):\n-    return a - b\n+    return a + b\n"
    )
    result = sandbox.run_patch_and_tests(patch, test_ids=["test_calc.py::test_add"])
    assert result.patch_applied is True
    assert result.passed is True
    assert "test_calc.py::test_add" in result.tests_passed


@pytest.mark.skipif(
    not _test_image_available(),
    reason=f"Test image '{TEST_IMAGE}' not built.",
)
def test_sandbox_reports_failure_for_wrong_patch():
    sandbox = DockerSandbox(image=TEST_IMAGE, timeout_seconds=30)
    wrong_patch = (
        "--- a/calc.py\n+++ b/calc.py\n@@ -1,2 +1,2 @@\n"
        "def add(a, b):\n-    return a - b\n+    return a * b\n"
    )
    result = sandbox.run_patch_and_tests(wrong_patch, test_ids=["test_calc.py::test_add"])
    assert result.patch_applied is True
    assert result.passed is False
    assert "test_calc.py::test_add" in result.tests_failed
