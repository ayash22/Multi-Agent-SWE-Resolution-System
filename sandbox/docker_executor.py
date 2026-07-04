"""
Docker sandbox executor: the ONLY place in this codebase where a generated
patch is ever applied and executed. Every run happens inside a freshly
created, resource- and network-restricted container that is destroyed
immediately after, so a hallucinated or malicious patch (e.g. one that tries
to `rm -rf` or exfiltrate data) can never touch the host or persist state
between runs.

Safety properties enforced here:
  - `network_disabled=True`      -- no outbound network from inside the sandbox
  - `mem_limit` / `nano_cpus`     -- resource caps to prevent fork-bombs / OOM
  - HARD, watchdog-thread-based 60s wall-clock timeout that fires
    unconditionally (see note below on why a naive "check the clock between
    output chunks" approach is not sufficient), container killed and removed
    if exceeded
  - a shell-level `timeout` wrapper around the test command as defense in
    depth, independent of the Python-side watchdog
  - container always removed in a `finally` block (`remove=True` + explicit
    `container.remove(force=True)` fallback), so no state leaks between runs
  - patch is written to a temp file and copied in via `put_archive`, never
    interpolated into a shell string (avoids shell-injection from patch
    content)

Why a watchdog thread and not just "check elapsed time in the read loop":
if a generated patch causes a test to hang and produce ZERO output (e.g. an
infinite loop with no print statements, or a deadlock), a loop of the form
`for chunk in exec_stream: ...; if time.time() > deadline: break` never gets
a chance to check the deadline, because iterating the generator blocks
indefinitely waiting for the next chunk that never arrives. A background
thread with `thread.join(timeout=...)` enforces the wall-clock limit
regardless of whether the sandboxed process ever produces output.
"""
from __future__ import annotations

import io
import tarfile
import threading
import time
from dataclasses import dataclass, field

import docker
from docker.errors import ContainerError, ImageNotFound

DEFAULT_TIMEOUT_SECONDS = 60
DEFAULT_MEM_LIMIT = "2g"
DEFAULT_NANO_CPUS = 2_000_000_000  # 2 CPUs
WATCHDOG_GRACE_SECONDS = 5  # extra time given to the kill+cleanup sequence itself


@dataclass
class SandboxResult:
    passed: bool
    exit_code: int
    stdout: str
    stderr: str
    tests_passed: list[str] = field(default_factory=list)
    tests_failed: list[str] = field(default_factory=list)
    timed_out: bool = False
    duration_seconds: float = 0.0
    patch_applied: bool = False


def _make_tar(file_name: str, content: bytes) -> io.BytesIO:
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w") as tar:
        info = tarfile.TarInfo(name=file_name)
        info.size = len(content)
        tar.addfile(info, io.BytesIO(content))
    stream.seek(0)
    return stream


def _parse_pytest_output(stdout: str) -> tuple[list[str], list[str]]:
    """Parses pytest's default short summary (`-v` output lines of the form
    `path::TestClass::test_name PASSED/FAILED`) into pass/fail test-id lists.
    Robust to pytest version differences since it only depends on the
    ' PASSED'/' FAILED' suffix pytest has used across all modern releases."""
    passed, failed = [], []
    for line in stdout.splitlines():
        line = line.strip()
        if " PASSED" in line:
            passed.append(line.split(" PASSED")[0].strip())
        elif " FAILED" in line:
            failed.append(line.split(" FAILED")[0].strip())
    return passed, failed


class DockerSandbox:
    def __init__(self, image: str, timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
                 mem_limit: str = DEFAULT_MEM_LIMIT, nano_cpus: int = DEFAULT_NANO_CPUS):
        self.client = docker.from_env()
        self.image = image
        self.timeout_seconds = timeout_seconds
        self.mem_limit = mem_limit
        self.nano_cpus = nano_cpus

    def _ensure_image(self) -> None:
        try:
            self.client.images.get(self.image)
        except ImageNotFound:
            raise RuntimeError(
                f"Sandbox image '{self.image}' not found locally. Build it first: "
                f"`docker build -t {self.image} -f sandbox/Dockerfile.sandbox "
                f"--build-arg REPO=<repo> --build-arg COMMIT=<commit> .`"
            )

    def run_patch_and_tests(
        self, patch_text: str, test_ids: list[str], repo_workdir: str = "/repo",
    ) -> SandboxResult:
        self._ensure_image()
        start = time.time()
        container = None
        try:
            container = self.client.containers.run(
                self.image,
                command="sleep infinity",
                detach=True,
                network_disabled=True,
                mem_limit=self.mem_limit,
                nano_cpus=self.nano_cpus,
                working_dir=repo_workdir,
            )

            # Copy the patch in as a file rather than interpolating it into a
            # shell command, to avoid any shell-injection risk from patch content.
            tar_stream = _make_tar("agent_patch.diff", patch_text.encode())
            container.put_archive(repo_workdir, tar_stream)

            apply_exit, apply_out = container.exec_run(
                "git apply --verbose agent_patch.diff", workdir=repo_workdir
            )
            patch_applied = apply_exit == 0
            if not patch_applied:
                return SandboxResult(
                    passed=False, exit_code=apply_exit,
                    stdout="", stderr=apply_out.decode(errors="ignore"),
                    patch_applied=False,
                    duration_seconds=time.time() - start,
                )

            test_target = " ".join(test_ids) if test_ids else ""
            # Defense in depth #1: a shell-level `timeout` wraps the test
            # command itself, so even if the Python-side watchdog below were
            # ever bypassed, the in-container process is still bounded.
            # `coreutils` (providing `timeout`) ships in python:*-slim by default.
            cmd = f"timeout {self.timeout_seconds}s pytest -v --no-header {test_target}".strip()

            exec_id = self.client.api.exec_create(container.id, cmd, workdir=repo_workdir)

            # Defense in depth #2 (the one that actually matters): run the
            # blocking exec_start call in a background thread and enforce
            # the wall-clock timeout with `thread.join(timeout=...)`. This
            # fires even if the sandboxed process produces zero output and
            # never enters a read loop that could check the clock -- see
            # the module docstring for why the naive "check between chunks"
            # approach is insufficient.
            result_holder: dict = {}

            def _run_exec():
                try:
                    output = self.client.api.exec_start(exec_id, stream=False)
                    result_holder["stdout"] = output.decode(errors="ignore")
                    result_holder["exit_code"] = self.client.api.exec_inspect(exec_id).get("ExitCode", -1)
                except Exception as exec_err:  # noqa: BLE001 -- surfaced via result_holder, not swallowed
                    result_holder["error"] = str(exec_err)

            worker = threading.Thread(target=_run_exec, daemon=True)
            worker.start()
            worker.join(timeout=self.timeout_seconds + WATCHDOG_GRACE_SECONDS)

            if worker.is_alive():
                # Hard timeout hit: the shell-level `timeout` wrapper above
                # should have already killed the test process, but if the
                # daemon call itself is stuck (e.g. a runaway subprocess
                # escaping timeout's supervision, or a Docker-side stall),
                # forcibly kill the container so this call can never hang
                # the caller indefinitely.
                try:
                    container.kill()
                except docker.errors.APIError:
                    pass
                worker.join(timeout=WATCHDOG_GRACE_SECONDS)
                return SandboxResult(
                    passed=False, exit_code=-1,
                    stdout=result_holder.get("stdout", ""),
                    stderr="Execution exceeded the hard timeout and the "
                           "sandbox container was forcibly killed.",
                    timed_out=True, patch_applied=True,
                    duration_seconds=time.time() - start,
                )

            if "error" in result_holder:
                return SandboxResult(
                    passed=False, exit_code=-1, stdout="",
                    stderr=f"Sandbox exec error: {result_holder['error']}",
                    patch_applied=True, duration_seconds=time.time() - start,
                )

            exit_code = result_holder.get("exit_code", -1)
            stdout = result_holder.get("stdout", "")
            # exit code 124 is `timeout`'s own signal that IT killed the
            # process -- treat this the same as our watchdog timing out.
            if exit_code == 124:
                return SandboxResult(
                    passed=False, exit_code=exit_code, stdout=stdout,
                    stderr=f"Test execution exceeded {self.timeout_seconds}s "
                           "and was killed by the in-container `timeout` wrapper.",
                    timed_out=True, patch_applied=True,
                    duration_seconds=time.time() - start,
                )

            tests_passed, tests_failed = _parse_pytest_output(stdout)

            return SandboxResult(
                passed=(exit_code == 0 and not tests_failed),
                exit_code=exit_code,
                stdout=stdout,
                stderr="",
                tests_passed=tests_passed,
                tests_failed=tests_failed,
                timed_out=False,
                patch_applied=True,
                duration_seconds=time.time() - start,
            )

        except ContainerError as e:
            return SandboxResult(
                passed=False, exit_code=e.exit_status,
                stdout="", stderr=str(e), duration_seconds=time.time() - start,
            )
        finally:
            if container is not None:
                try:
                    container.remove(force=True)
                except docker.errors.APIError:
                    pass


def run_candidate_in_sandbox(
    image: str, patch_text: str, test_ids: list[str],
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> SandboxResult:
    """Convenience wrapper used by the test_runner_agent node."""
    sandbox = DockerSandbox(image=image, timeout_seconds=timeout_seconds)
    return sandbox.run_patch_and_tests(patch_text, test_ids)
