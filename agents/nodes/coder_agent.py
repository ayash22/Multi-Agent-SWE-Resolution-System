"""
Coder agent (GPT-4o primary patch generator): given the issue, plan, and
retrieved code context, generates a minimal unified-diff patch.

This node is called twice in the graph (run1 at low temperature for a
focused, conservative patch; run2 at higher temperature with a rephrased
instruction for a more exploratory alternative), producing two of the three
best-of-N candidates. The third comes from llama_coder_agent.py.
"""
from __future__ import annotations

import os
import re
import subprocess
import tempfile

from agents.state import PatchCandidateDict, SWEAgentState

CODER_SYSTEM_PROMPT = """\
You are an expert software engineer fixing a real GitHub issue.

Given a GitHub issue, a fix plan, and the relevant code from the repository,
generate a minimal, correct code patch in unified diff format that fixes the
issue.

Rules:
- The patch MUST be directly applicable with `git apply` (correct file paths,
  correct context lines, correct hunk headers).
- Do not change more code than necessary to fix the issue.
- Do not add unnecessary imports, refactor unrelated code, or reformat
  untouched lines.
- Preserve the existing code style (indentation, quote style, etc.) exactly.
- Output ONLY the diff, inside a single ```diff ... ``` code block. No prose
  before or after.

Grounding rules -- these exist to prevent fabricated patches that look
plausible but don't correspond to the real codebase:
- Only reference file paths, function names, class names, and variable names
  that literally appear in the "## Relevant code" section below or are
  explicitly named in the issue text. Do not invent helper functions,
  imports, config flags, or APIs that are not shown to you, even if they
  seem like a natural fit for the fix.
- Every context line (lines without a leading + or -) in your diff hunks
  must be copied verbatim from the "## Relevant code" section -- do not
  paraphrase or reconstruct code from memory of how similar code "usually"
  looks in this framework.
- If the code you would need to see to fix this issue correctly was not
  included in the "## Relevant code" section, make the most conservative
  possible edit to the code you WERE shown, and do not fabricate the
  contents of files you were not given.
"""

# Bounds response length -- SWE-bench-Lite-style fixes are almost always
# small; capping this is a guardrail against runaway/degenerate generation
# producing an implausibly large diff, not a constraint we expect to bind
# on genuinely correct patches.
CODER_MAX_OUTPUT_TOKENS = 2000
CODER_REQUEST_TIMEOUT_SECONDS = 90

# A patch that touches more than this many changed lines is treated as
# suspicious (likely hallucinated, or the model attempting an inappropriately
# broad refactor instead of a minimal fix) and is rejected before it's ever
# sent to the sandbox -- both to save a sandbox run and because "large diff"
# is itself a strong signal of an ungrounded response for this benchmark.
MAX_PLAUSIBLE_PATCH_CHANGED_LINES = 300


def _format_context(retrieved_chunks: list[dict]) -> str:
    blocks = []
    for c in retrieved_chunks:
        header = f"# {c['file_path']} :: {c.get('name', '')} (lines {c['start_line']}-{c['end_line']})"
        blocks.append(f"{header}\n{c['code']}")
    return "\n\n".join(blocks)


def _build_user_prompt(state: SWEAgentState, run_variant: str) -> str:
    plan = state.get("plan", {})
    context = _format_context(state.get("retrieved_chunks", []))
    variant_hint = ""
    if run_variant == "run2":
        variant_hint = (
            "\nNote: consider whether there is an alternative, equally minimal "
            "way to fix this that touches different lines/files than the most "
            "obvious approach, if one exists and is equally correct."
        )
    return (
        f"## Repository\n{state['repo']}\n\n"
        f"## Issue\n{state['issue_text']}\n\n"
        f"## Fix plan\n"
        f"Summary: {plan.get('issue_summary', '')}\n"
        f"Strategy: {plan.get('fix_strategy', '')}\n"
        f"Test hints: {plan.get('test_hints', '')}\n\n"
        f"## Relevant code\n{context}"
        f"{variant_hint}"
    )


def _call_gpt4o(system_prompt: str, user_prompt: str, temperature: float) -> str:
    from openai import OpenAI
    client = OpenAI(timeout=CODER_REQUEST_TIMEOUT_SECONDS)
    resp = client.chat.completions.create(
        model="gpt-4o",
        temperature=temperature,
        max_tokens=CODER_MAX_OUTPUT_TOKENS,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    return resp.choices[0].message.content


def extract_diff(raw_response: str) -> str:
    match = re.search(r"```diff\s*\n(.*?)```", raw_response, re.DOTALL)
    if match:
        return match.group(1).strip()
    # fall back: model may have omitted the fence despite instructions
    if raw_response.strip().startswith(("diff --git", "--- ")):
        return raw_response.strip()
    raise ValueError(f"Could not extract a unified diff from response: {raw_response[:300]!r}")


def validate_syntax(patch_text: str) -> bool:
    """A patch is syntactically valid if it parses as a sequence of unified
    diff hunks: has file headers and at least one @@ hunk with +/- lines."""
    has_file_header = bool(re.search(r"^(diff --git|--- )", patch_text, re.MULTILINE))
    has_hunk = bool(re.search(r"^@@ .+ @@", patch_text, re.MULTILINE))
    return has_file_header and has_hunk


def count_changed_lines(patch_text: str) -> int:
    return sum(
        1 for line in patch_text.splitlines()
        if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))
    )


def is_implausibly_large(patch_text: str, max_lines: int = MAX_PLAUSIBLE_PATCH_CHANGED_LINES) -> bool:
    """Guardrail against runaway/hallucinated generation: a patch this large
    for a SWE-bench-Lite-style minimal fix is far more likely to be a
    degenerate or ungrounded response than a genuinely necessary large
    change, so it's rejected before ever reaching the sandbox."""
    return count_changed_lines(patch_text) > max_lines


def check_applies_cleanly(patch_text: str, repo_local_path: str) -> bool:
    """Dry-runs `git apply --check` against the repo working copy to confirm
    the patch would apply without touching any files."""
    with tempfile.NamedTemporaryFile("w", suffix=".patch", delete=False) as f:
        f.write(patch_text if patch_text.endswith("\n") else patch_text + "\n")
        patch_path = f.name
    try:
        result = subprocess.run(
            ["git", "apply", "--check", patch_path],
            cwd=repo_local_path, capture_output=True, text=True,
        )
        return result.returncode == 0
    finally:
        os.unlink(patch_path)


def generate_patch(state: SWEAgentState, run_variant: str, candidate_id: str) -> PatchCandidateDict:
    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError(
            "OPENAI_API_KEY is not set. The coder agent calls GPT-4o and "
            "requires a valid API key -- see README.md 'Configuration'."
        )

    temperature = 0.1 if run_variant == "run1" else 0.6
    user_prompt = _build_user_prompt(state, run_variant)
    raw = _call_gpt4o(CODER_SYSTEM_PROMPT, user_prompt, temperature)

    try:
        patch_text = extract_diff(raw)
        syntax_valid = validate_syntax(patch_text)
    except ValueError:
        patch_text = raw
        syntax_valid = False

    if syntax_valid and is_implausibly_large(patch_text):
        # Guardrail: don't spend a sandbox run on a patch that's already a
        # strong signal of ungrounded/runaway generation. It's still
        # returned (visible in the UI for debugging) but marked invalid so
        # the ranker and verifier both reject it outright.
        syntax_valid = False

    applies = False
    if syntax_valid and state.get("repo_local_path"):
        applies = check_applies_cleanly(patch_text, state["repo_local_path"])

    return PatchCandidateDict(
        candidate_id=candidate_id,
        source=f"gpt4o_{run_variant}",
        patch_text=patch_text,
        syntax_valid=syntax_valid,
        applies_cleanly=applies,
        test_result=None,
        rank_score=None,
        rank_features=None,
    )


def coder_node_run1(state: SWEAgentState) -> dict:
    candidate = generate_patch(state, "run1", candidate_id="gpt4o_run1")
    return {"candidates": [candidate]}


def coder_node_run2(state: SWEAgentState) -> dict:
    candidate = generate_patch(state, "run2", candidate_id="gpt4o_run2")
    return {"candidates": [candidate]}
