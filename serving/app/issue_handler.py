from __future__ import annotations

import os
import re
import subprocess
import tempfile
import uuid

import requests

from agents.graph import run_instance
from serving.app.schemas import (
    IssueRequest,
    IssueRunResponse,
    PatchCandidateResponse,
    PipelineStepStatus,
)

GITHUB_ISSUE_URL_RE = re.compile(
    r"github\.com/(?P<owner>[\w.-]+)/(?P<repo>[\w.-]+)/issues/(?P<number>\d+)"
)

PIPELINE_STEPS = [
    "planner", "retrieval", "coder_gpt4o_run1", "coder_gpt4o_run2",
    "llama_coder", "test_runner_run1", "test_runner_run2", "test_runner_llama",
    "verifier", "patch_ranker",
]


def fetch_issue_text_from_url(issue_url: str) -> str:
    match = GITHUB_ISSUE_URL_RE.search(issue_url)
    if not match:
        raise ValueError(f"Not a recognizable GitHub issue URL: {issue_url}")
    owner, repo, number = match.group("owner"), match.group("repo"), match.group("number")

    api_url = f"https://api.github.com/repos/{owner}/{repo}/issues/{number}"
    headers = {"Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    resp = requests.get(api_url, headers=headers, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    return f"{data['title']}\n\n{data.get('body') or ''}"


def clone_repo_at_commit(repo: str, base_commit: str) -> str:
    workdir = tempfile.mkdtemp(prefix="swe_issue_repo_")
    subprocess.run(["git", "clone", "--quiet", f"https://github.com/{repo}.git", workdir], check=True)
    subprocess.run(["git", "-C", workdir, "checkout", "--quiet", base_commit], check=True)
    return workdir


def handle_issue(request: IssueRequest) -> IssueRunResponse:
    if request.issue_url and not request.issue_text:
        issue_text = fetch_issue_text_from_url(request.issue_url)
    elif request.issue_text:
        issue_text = request.issue_text
    else:
        raise ValueError("Either issue_text or issue_url must be provided.")

    instance_id = f"live-{uuid.uuid4().hex[:8]}"
    repo_local_path = clone_repo_at_commit(request.repo, request.base_commit)

    final_state = run_instance({
        "instance_id": instance_id,
        "repo": request.repo,
        "base_commit": request.base_commit,
        "issue_text": issue_text,
        "fail_to_pass_tests": request.fail_to_pass_tests,
        "pass_to_pass_tests": request.pass_to_pass_tests,
        "repo_local_path": repo_local_path,
    })

    selected_id = (final_state.get("selected_candidate") or {}).get("candidate_id")
    candidates_resp = []
    for c in final_state.get("resolved_candidates", []):
        test_result = c.get("test_result") or {}
        candidates_resp.append(PatchCandidateResponse(
            candidate_id=c["candidate_id"],
            source=c["source"],
            patch_text=c["patch_text"],
            syntax_valid=c["syntax_valid"],
            applies_cleanly=c["applies_cleanly"],
            tests_passed=test_result.get("tests_passed", []),
            tests_failed=test_result.get("tests_failed", []),
            rank_score=c.get("rank_score"),
            is_selected=(c["candidate_id"] == selected_id),
        ))

    pipeline_steps = [
        PipelineStepStatus(step=s, status="done") for s in PIPELINE_STEPS
    ]

    return IssueRunResponse(
        instance_id=instance_id,
        status=final_state.get("status", "unknown"),
        plan=final_state.get("plan"),
        retrieved_chunks=final_state.get("retrieved_chunks", []),
        candidates=candidates_resp,
        final_patch=final_state.get("final_patch"),
        resolved=final_state.get("resolved"),
        explanation=final_state.get("explanation"),
        pipeline_steps=pipeline_steps,
    )
