from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class IssueRequest(BaseModel):
    repo: str = Field(..., description="e.g. 'django/django'")
    issue_text: str | None = None
    issue_url: str | None = Field(
        None, description="GitHub issue URL; if given, text is fetched via the GitHub API"
    )
    base_commit: str = Field(..., description="Commit SHA the repo should be checked out at")
    fail_to_pass_tests: list[str] = []
    pass_to_pass_tests: list[str] = []


class PipelineStepStatus(BaseModel):
    step: str
    status: Literal["pending", "running", "done", "failed"]
    input_summary: str | None = None
    output_summary: str | None = None


class PatchCandidateResponse(BaseModel):
    candidate_id: str
    source: str
    patch_text: str
    syntax_valid: bool
    applies_cleanly: bool
    tests_passed: list[str] = []
    tests_failed: list[str] = []
    rank_score: float | None = None
    is_selected: bool = False


class IssueRunResponse(BaseModel):
    instance_id: str
    status: str
    plan: dict[str, Any] | None = None
    retrieved_chunks: list[dict[str, Any]] = []
    candidates: list[PatchCandidateResponse] = []
    final_patch: str | None = None
    resolved: bool | None = None
    explanation: str | None = None
    pipeline_steps: list[PipelineStepStatus] = []


class EvalSummaryResponse(BaseModel):
    baseline_resolved: int
    full_system_resolved: int
    total_instances: int
    by_repo: dict[str, dict[str, int]]
