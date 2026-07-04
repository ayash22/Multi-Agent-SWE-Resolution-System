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

After your reasoning, output ONLY a JSON object (no markdown fences, no prose
before or after) with exactly these keys:
{
  "issue_summary": "<one sentence describing the bug>",
  "likely_files": ["<file1.py>", "<file2.py>"],
  "fix_strategy": "<detailed natural-language plan for the fix, step by step>",
  "test_hints": "<what the failing tests are checking for>"
}
"""


def _call_gpt4o(issue_text: str, repo: str) -> str:
    from openai import OpenAI
    client = OpenAI()
    resp = client.chat.completions.create(
        model="gpt-4o",
        temperature=0.2,
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
    return PlanDict(
        issue_summary=parsed.get("issue_summary", ""),
        likely_files=parsed.get("likely_files", []),
        fix_strategy=parsed.get("fix_strategy", ""),
        test_hints=parsed.get("test_hints", ""),
    )


def planner_node(state: SWEAgentState) -> dict:
    """LangGraph node entrypoint: reads `issue_text`/`repo` from state, writes
    `plan` and `status` back."""
    plan = plan_issue(state["issue_text"], state["repo"])
    return {"plan": plan, "status": "retrieving"}
