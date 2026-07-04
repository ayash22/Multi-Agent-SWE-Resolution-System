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


def test_watchdog_fires_on_hang_with_zero_output(monkeypatch):
    """Regression test for a real bug found during audit: the original
    implementation only checked the wall-clock deadline *between* chunks
    read from the exec stream, so a hung process producing ZERO output
    would never trigger the timeout (the read loop blocks indefinitely on
    the next chunk that never arrives). This test simulates exactly that
    case -- an exec_start call that never returns -- against a mocked
    Docker client, and asserts the watchdog thread still forces a timed-out
    result within a bounded, short wall-clock window."""
    import threading
    import time as time_module

    from sandbox.docker_executor import DockerSandbox

    sandbox = DockerSandbox.__new__(DockerSandbox)  # bypass __init__'s docker.from_env()
    sandbox.image = "fake-image"
    sandbox.timeout_seconds = 1  # keep the test fast
    sandbox.mem_limit = "2g"
    sandbox.nano_cpus = 2_000_000_000

    class FakeContainer:
        def __init__(self):
            self.killed = False
            self.id = "fake-container-id"

        def put_archive(self, *a, **kw):
            pass

        def exec_run(self, *a, **kw):
            return (0, b"")  # patch applies "cleanly"

        def kill(self):
            self.killed = True

        def remove(self, force=False):
            pass

    class FakeAPI:
        def exec_create(self, *a, **kw):
            return "fake-exec-id"

        def exec_start(self, *a, **kw):
            # Simulates a hung process: never returns within any reasonable
            # test window. The watchdog's thread.join(timeout=...) must
            # still return control to the caller.
            hang_forever = threading.Event()
            hang_forever.wait(timeout=30)  # far longer than sandbox.timeout_seconds
            return b""

        def exec_inspect(self, *a, **kw):
            return {"ExitCode": -1}

    class FakeClient:
        def __init__(self):
            self.api = FakeAPI()

        def images(self):
            return self

        def get(self, *a, **kw):
            return object()

        def containers(self):
            return self

        def run(self, *a, **kw):
            return FakeContainer()

    fake_client = FakeClient()
    fake_client.images = type("X", (), {"get": lambda self, *a, **kw: object()})()
    fake_client.containers = type("X", (), {"run": lambda self, *a, **kw: FakeContainer()})()
    sandbox.client = fake_client

    start = time_module.time()
    result = sandbox.run_patch_and_tests("--- a/foo.py\n+++ b/foo.py\n@@ -1 +1 @@\n-x\n+y\n", ["t1"])
    elapsed = time_module.time() - start

    assert result.timed_out is True
    assert result.passed is False
    # The watchdog must return well before the fake hang's 30s wait would --
    # bounded by timeout_seconds + WATCHDOG_GRACE_SECONDS (1 + 5 = 6s), with
    # generous slack for test-runner overhead.
    assert elapsed < 15, (
        f"Watchdog did not enforce the timeout: took {elapsed:.1f}s "
        "(the original chunk-loop-based implementation would hang here "
        "for the full 30s simulated freeze)."
    )
