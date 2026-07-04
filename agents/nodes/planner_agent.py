"""
Planner agent: given the raw GitHub issue text, uses GPT-4o with an explicit
chain-of-thought prompt to produce a structured fix plan that downstream
agents (retrieval, coder) condition on.
"""
from __future__ import annotations

import json
import os

from agents.state import PlanDict, SWEAgentState

PLANNER_SYSTEM_PROMPT = """\
You are a senior software engineer triaging a GitHub issue before writing a fix.

Think step by step, in this exact order:
1. First, explain what the bug is, in plain language, based only on the issue text.
2. Then, explain where in the codebase it likely lives -- reason about module/package
   names, class names, or function names mentioned or implied by the issue and any
   stack trace it contains.
3. Then, describe the fix approach step by step: what needs to change and why,
   without writing actual code yet.
4. Finally, describe what the failing test(s) are likely checking for, so a
   test-writer or verifier agent knows what "fixed" looks like.

Grounding rules -- follow these strictly to avoid guessing:
- You have NOT been shown the actual source code yet at this stage, only the
  issue text. Do not assert specific function names, class names, or exact
  file contents as fact -- phrase anything you can't verify from the issue
  text itself as a hypothesis (e.g. "likely in", "probably", "based on the
  stack trace").
- For "likely_files": only list a file path if it is explicitly mentioned in
  the issue text (including a stack trace) or can be directly derived from a
  module/class name that IS mentioned. If you cannot identify any concrete
  file path this way, return an empty list rather than inventing a
  plausible-sounding but fabricated path -- a downstream retrieval step will
  search the actual codebase regardless, so a wrong guess here is worse than
  no guess.
- Do not invent line numbers, exact error messages, or code snippets that
  were not given to you.

After your reasoning, output ONLY a JSON object (no markdown fences, no prose
before or after) with exactly these keys:
{
  "issue_summary": "<one sentence describing the bug>",
  "likely_files": ["<file1.py>", "<file2.py>"],
  "fix_strategy": "<detailed natural-language plan for the fix, step by step>",
  "test_hints": "<what the failing tests are checking for>"
}
"""

# Bounds the planner's response length. A fix plan should always be a short
# paragraph, not an essay -- capping this is a guardrail against runaway or
# degenerate generation, not a functional constraint we expect to hit in
# normal operation.
PLANNER_MAX_OUTPUT_TOKENS = 1000
# Hard wall-clock bound on the API call itself, independent of any retry
# logic upstream, so a stalled request can never hang the pipeline.
PLANNER_REQUEST_TIMEOUT_SECONDS = 60

REQUIRED_PLAN_KEYS = {"issue_summary", "likely_files", "fix_strategy", "test_hints"}


def _call_gpt4o(issue_text: str, repo: str) -> str:
    from openai import OpenAI
    client = OpenAI(timeout=PLANNER_REQUEST_TIMEOUT_SECONDS)
    resp = client.chat.completions.create(
        model="gpt-4o",
        temperature=0.2,
        max_tokens=PLANNER_MAX_OUTPUT_TOKENS,
        messages=[
            {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
            {"role": "user", "content": f"Repository: {repo}\n\nIssue:\n{issue_text}"},
        ],
    )
    return resp.choices[0].message.content


def _extract_json(raw: str) -> dict:
    """GPT-4o occasionally wraps JSON in markdown fences despite instructions
    not to; strip those defensively before parsing."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[len("json"):]
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"No JSON object found in planner output: {raw!r}")
    return json.loads(text[start:end + 1])


def plan_issue(issue_text: str, repo: str) -> PlanDict:
    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError(
            "OPENAI_API_KEY is not set. The planner agent calls GPT-4o and "
            "requires a valid API key -- see README.md 'Configuration'."
        )
    raw = _call_gpt4o(issue_text, repo)
    parsed = _extract_json(raw)

    missing = REQUIRED_PLAN_KEYS - set(parsed.keys())
    if missing:
        raise ValueError(
            f"Planner response is missing required keys {missing}. "
            f"Raw response: {raw[:500]!r}"
        )
    if not isinstance(parsed.get("likely_files"), list):
        raise ValueError(
            f"Planner response's 'likely_files' must be a list, got "
            f"{type(parsed.get('likely_files')).__name__}. This usually means "
            "the model produced a malformed response rather than following "
            "the required schema."
        )

    return PlanDict(
        issue_summary=parsed["issue_summary"],
        likely_files=parsed["likely_files"],
        fix_strategy=parsed["fix_strategy"],
        test_hints=parsed["test_hints"],
    )


def planner_node(state: SWEAgentState) -> dict:
    """LangGraph node entrypoint: reads `issue_text`/`repo` from state, writes
    `plan` and `status` back."""
    plan = plan_issue(state["issue_text"], state["repo"])
    return {"plan": plan, "status": "retrieving"}
