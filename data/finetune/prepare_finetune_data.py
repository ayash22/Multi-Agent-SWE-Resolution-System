"""
Formats raw (issue, code_context, patch) trajectories into the chat-style
SFT format expected by TRL's SFTTrainer for Llama-3-8B-Instruct fine-tuning.

Each example becomes a single Llama-3 chat-formatted string:

<|begin_of_text|><|start_header_id|>system<|end_header_id|>
You are an expert software engineer. Given a GitHub issue and relevant code
context, produce a minimal, correct unified diff patch that resolves the
issue.<|eot_id|>
<|start_header_id|>user<|end_header_id|>
## Issue
{issue_text}

## Relevant code
{code_context}<|eot_id|>
<|start_header_id|>assistant<|end_header_id|>
```diff
{patch}
```<|eot_id|>

Truncation strategy (target: 4096-token sequences):
  - Reserve ~256 tokens for the patch (assistant turn) -- patches rarely
    exceed this for SWE-bench-Lite-style fixes.
  - Reserve ~256 tokens for system + issue text overhead.
  - Truncate code_context to fit the remainder, keeping the *tail* of each
    file chunk (closer to typical edit locations) rather than naive
    head-truncation.

Usage:
    python prepare_finetune_data.py \
        --input data/finetune/raw_trajectories.jsonl \
        --output data/finetune/sft_dataset.jsonl \
        --tokenizer meta-llama/Meta-Llama-3-8B-Instruct \
        --max-seq-len 4096
"""
import argparse
import json

SYSTEM_PROMPT = (
    "You are an expert software engineer. Given a GitHub issue and relevant "
    "code context, produce a minimal, correct unified diff patch that "
    "resolves the issue. The patch must be directly applicable with "
    "`git apply`. Do not change more code than necessary."
)


def build_chat_text(issue_text: str, code_context: str, patch: str) -> str:
    return (
        "<|begin_of_text|><|start_header_id|>system<|end_header_id|>\n\n"
        f"{SYSTEM_PROMPT}<|eot_id|>"
        "<|start_header_id|>user<|end_header_id|>\n\n"
        f"## Issue\n{issue_text}\n\n## Relevant code\n{code_context}<|eot_id|>"
        "<|start_header_id|>assistant<|end_header_id|>\n\n"
        f"```diff\n{patch}\n```<|eot_id|>"
    )


def truncate_context(code_context: str, tokenizer, budget_tokens: int) -> str:
    if not code_context:
        return ""
    files = code_context.split("### FILE:")
    files = [f"### FILE:{f}" if f.strip() else f for f in files if f.strip()]
    if not files:
        return code_context

    per_file_budget = max(64, budget_tokens // max(1, len(files)))
    kept = []
    for f in files:
        ids = tokenizer.encode(f, add_special_tokens=False)
        if len(ids) <= per_file_budget:
            kept.append(f)
        else:
            # Keep the tail: edits are usually near the bottom half of a
            # relevant function/file that the retriever pulled in.
            tail_ids = ids[-per_file_budget:]
            kept.append(tokenizer.decode(tail_ids))
    return "\n\n".join(kept)


def main(args):
    try:
        from transformers import AutoTokenizer
        tokenizer = AutoTokenizer.from_pretrained(args.tokenizer)
    except Exception as e:
        print(
            f"Could not load tokenizer '{args.tokenizer}' ({e}). "
            "Falling back to a simple whitespace-token approximation for "
            "truncation budgeting -- exact SFT tokenization still happens "
            "correctly inside SFTTrainer at train time."
        )
        tokenizer = None

    n_written = 0
    with open(args.input) as fin, open(args.output, "w") as fout:
        for line in fin:
            ex = json.loads(line)
            issue_text = ex.get("issue_text", "") or ""
            patch = ex.get("patch", "") or ""
            code_context = ex.get("code_context", "") or ""

            if not patch.strip():
                continue

            if tokenizer is not None:
                reserved = 512  # system + issue + patch + special tokens
                budget = max(256, args.max_seq_len - reserved)
                code_context = truncate_context(code_context, tokenizer, budget)
            else:
                # crude char-based fallback (~4 chars/token)
                budget_chars = max(1024, (args.max_seq_len - 512) * 4)
                code_context = code_context[-budget_chars:]

            text = build_chat_text(issue_text, code_context, patch)
            fout.write(json.dumps({"text": text, "instance_id": ex.get("instance_id"),
                                    "source": ex.get("source")}) + "\n")
            n_written += 1

    print(f"Wrote {n_written} SFT-formatted examples to {args.output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/finetune/raw_trajectories.jsonl")
    parser.add_argument("--output", default="data/finetune/sft_dataset.jsonl")
    parser.add_argument("--tokenizer", default="meta-llama/Meta-Llama-3-8B-Instruct")
    parser.add_argument("--max-seq-len", type=int, default=4096)
    main(parser.parse_args())
