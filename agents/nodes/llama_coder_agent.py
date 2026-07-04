"""
Fine-tuned Llama-3-8B coder agent: the third best-of-N candidate generator.

Calls a locally-served model rather than the OpenAI API:
  - Dev:        Ollama (`ollama serve`, model pulled/created from the merged
                QLoRA weights -- see finetuning/merge_weights.py and the
                Modelfile it emits).
  - Production: vLLM OpenAI-compatible server
                (`python -m vllm.entrypoints.openai.api_server --model <merged_dir>`),
                which exposes the same `/v1/chat/completions` schema as OpenAI,
                so this node can reuse an OpenAI-compatible client either way.

If no fine-tuned checkpoint exists yet (e.g. fine-tuning was run in the cloud
and the merged weights haven't been copied to this machine), this node
transparently falls back to the base `llama3:8b-instruct` model via Ollama
and tags the candidate's source accordingly so the frontend/report can be
honest about which weights actually produced the patch.
"""
from __future__ import annotations

import os
import re

import requests

from agents.nodes.coder_agent import (
    _format_context,
    check_applies_cleanly,
    is_implausibly_large,
    validate_syntax,
)
from agents.state import PatchCandidateDict, SWEAgentState

LLAMA_SERVER_URL = os.environ.get("LLAMA_SERVER_URL", "http://localhost:11434")
LLAMA_MODEL_NAME = os.environ.get("LLAMA_MODEL_NAME", "swe-llama3-qlora")
LLAMA_BASE_FALLBACK = os.environ.get("LLAMA_BASE_FALLBACK", "llama3:8b-instruct")
LLAMA_BACKEND = os.environ.get("LLAMA_BACKEND", "ollama")  # "ollama" | "vllm"

# Smaller open-weight models (Llama-3-8B included) are meaningfully more
# prone than GPT-4o to degenerate repetition loops -- e.g. repeating the
# same line or token sequence until the context window is exhausted. A hard
# output-token cap and an explicit repetition penalty are the two concrete
# guardrails against that failure mode; the stop sequence below matches the
# fine-tuning chat format (see data/finetune/prepare_finetune_data.py) so
# generation halts at the natural end of the assistant turn rather than
# continuing to hallucinate additional unrelated content.
LLAMA_MAX_OUTPUT_TOKENS = 1500
LLAMA_REPETITION_PENALTY = 1.15
LLAMA_STOP_SEQUENCES = ["<|eot_id|>"]
LLAMA_REQUEST_TIMEOUT_SECONDS = 120

SYSTEM_PROMPT = (
    "You are an expert software engineer. Given a GitHub issue and relevant "
    "code context, produce a minimal, correct unified diff patch that "
    "resolves the issue. The patch must be directly applicable with "
    "`git apply`. Do not change more code than necessary.\n\n"
    "Grounding rules: only reference file paths, function names, and code "
    "that literally appear in the provided context below or are explicitly "
    "named in the issue text. Do not invent helper functions, imports, or "
    "APIs that are not shown to you. Every unchanged (context) line in your "
    "diff hunks must be copied verbatim from the code you were given, not "
    "reconstructed from memory. Output ONLY the diff, once, inside a single "
    "```diff ... ``` block -- do not repeat the diff or continue generating "
    "after it is complete."
)


def _model_is_available(model_name: str) -> bool:
    try:
        resp = requests.get(f"{LLAMA_SERVER_URL}/api/tags", timeout=5)
        resp.raise_for_status()
        tags = [m["name"] for m in resp.json().get("models", [])]
        return any(model_name in t for t in tags)
    except requests.RequestException:
        return False


def _call_ollama(model_name: str, prompt: str) -> str:
    resp = requests.post(
        f"{LLAMA_SERVER_URL}/api/chat",
        json={
            "model": model_name,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "stream": False,
            "options": {
                "temperature": 0.2,
                "num_ctx": 4096,
                # Hard cap on generated tokens -- guardrail against
                # repetition loops / runaway generation (see module docstring).
                "num_predict": LLAMA_MAX_OUTPUT_TOKENS,
                "repeat_penalty": LLAMA_REPETITION_PENALTY,
                "stop": LLAMA_STOP_SEQUENCES,
            },
        },
        timeout=LLAMA_REQUEST_TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    return resp.json()["message"]["content"]


def _call_vllm(model_name: str, prompt: str) -> str:
    resp = requests.post(
        f"{LLAMA_SERVER_URL}/v1/chat/completions",
        json={
            "model": model_name,
            "temperature": 0.2,
            "max_tokens": LLAMA_MAX_OUTPUT_TOKENS,
            # vLLM's OpenAI-compatible endpoint supports repetition_penalty
            # as an extra (non-standard-OpenAI) field, same rationale as
            # the Ollama `repeat_penalty` above.
            "repetition_penalty": LLAMA_REPETITION_PENALTY,
            "stop": LLAMA_STOP_SEQUENCES,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        },
        timeout=LLAMA_REQUEST_TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def _build_prompt(state: SWEAgentState) -> str:
    plan = state.get("plan", {})
    context = _format_context(state.get("retrieved_chunks", []))
    return (
        f"## Issue\n{state['issue_text']}\n\n"
        f"## Fix plan\n{plan.get('fix_strategy', '')}\n\n"
        f"## Relevant code\n{context}"
    )


def _extract_diff(raw: str) -> str:
    match = re.search(r"```diff\s*\n(.*?)```", raw, re.DOTALL)
    if match:
        return match.group(1).strip()
    if raw.strip().startswith(("diff --git", "--- ")):
        return raw.strip()
    return raw


def generate_patch_llama(state: SWEAgentState) -> PatchCandidateDict:
    finetuned_available = LLAMA_BACKEND == "vllm" or _model_is_available(LLAMA_MODEL_NAME)
    model_name = LLAMA_MODEL_NAME if finetuned_available else LLAMA_BASE_FALLBACK
    source = "llama3_finetuned" if finetuned_available else "llama3_base_fallback"

    prompt = _build_prompt(state)
    try:
        if LLAMA_BACKEND == "vllm":
            raw = _call_vllm(model_name, prompt)
        else:
            raw = _call_ollama(model_name, prompt)
    except requests.RequestException as e:
        # Local model server unreachable: return a clearly-marked non-viable
        # candidate rather than crashing the whole graph run. The patch
        # ranker will naturally score this last since it fails
        # syntax/apply checks.
        return PatchCandidateDict(
            candidate_id="llama3_coder",
            source=source,
            patch_text=f"# ERROR: could not reach Llama server at {LLAMA_SERVER_URL}: {e}",
            syntax_valid=False,
            applies_cleanly=False,
            test_result=None,
            rank_score=None,
            rank_features=None,
        )

    patch_text = _extract_diff(raw)
    syntax_valid = validate_syntax(patch_text)
    if syntax_valid and is_implausibly_large(patch_text):
        syntax_valid = False

    applies = False
    if syntax_valid and state.get("repo_local_path"):
        applies = check_applies_cleanly(patch_text, state["repo_local_path"])

    return PatchCandidateDict(
        candidate_id="llama3_coder",
        source=source,
        patch_text=patch_text,
        syntax_valid=syntax_valid,
        applies_cleanly=applies,
        test_result=None,
        rank_score=None,
        rank_features=None,
    )


def llama_coder_node(state: SWEAgentState) -> dict:
    candidate = generate_patch_llama(state)
    return {"candidates": [candidate]}
