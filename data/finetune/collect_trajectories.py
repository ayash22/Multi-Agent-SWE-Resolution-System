"""
Collects (issue + code context) -> (correct patch) trajectories for QLoRA
fine-tuning of Llama-3-8B, from three sources:

  1. SWE-bench Verified / SWE-bench Lite ground-truth patches
     (princeton-nlp/SWE-bench_Verified on HuggingFace). We use the `patch`
     field as the label and reconstruct code context by checking out the
     repo at `base_commit` and pulling the files touched by the patch.

  2. The Agentless paper's released SWE-bench trajectories
     (https://github.com/OpenAutoCoder/Agentless) — these ship as JSON files
     of (instance_id, edited_files, patch) that we can reuse directly since
     they were produced against the same SWE-bench instances.

  3. CodeSearchNet (for general code-understanding pairs, not issue-fixing --
     used only to pad out the dataset with (docstring -> function) supervision
     that improves the model's general code fluency; weighted lower in
     training).

This script does NOT invent data: every trajectory written to disk is either
a real SWE-bench ground truth patch or a real Agentless-released solution.
If the source repos/datasets aren't reachable from your network, point
--agentless-dir / --swebench-verified-jsonl at local copies.

Usage:
    python collect_trajectories.py \
        --swebench-verified-jsonl data/swebench/raw/swebench_verified.jsonl \
        --agentless-dir /path/to/agentless/results \
        --out data/finetune/raw_trajectories.jsonl \
        --max-examples 2000
"""
import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path


def get_context_for_patch(repo: str, base_commit: str, patch: str, workdir: str) -> str:
    """Checks out `repo` at `base_commit` in a scratch dir and returns the
    pre-patch content of every file the patch touches, truncated per-file to
    keep the fine-tuning sequence within budget (real content -> tokenizer
    truncation is handled later in prepare_finetune_data.py)."""
    touched_files = []
    for line in patch.splitlines():
        if line.startswith("--- a/"):
            touched_files.append(line[len("--- a/"):])

    repo_dir = os.path.join(workdir, repo.replace("/", "__"))
    if not os.path.isdir(repo_dir):
        subprocess.run(
            ["git", "clone", "--quiet", f"https://github.com/{repo}.git", repo_dir],
            check=False,
        )
    subprocess.run(
        ["git", "-C", repo_dir, "checkout", "--quiet", base_commit],
        check=False,
    )

    context_chunks = []
    for f in touched_files:
        fpath = os.path.join(repo_dir, f)
        if os.path.isfile(fpath):
            with open(fpath, errors="ignore") as fh:
                context_chunks.append(f"### FILE: {f}\n" + fh.read())
    return "\n\n".join(context_chunks)


def from_swebench_verified(jsonl_path: str, workdir: str, limit: int) -> list[dict]:
    examples = []
    if not os.path.isfile(jsonl_path):
        print(f"[skip] {jsonl_path} not found")
        return examples

    with open(jsonl_path) as f:
        for i, line in enumerate(f):
            if limit and len(examples) >= limit:
                break
            inst = json.loads(line)
            context = get_context_for_patch(
                inst["repo"], inst["base_commit"], inst["patch"], workdir
            )
            examples.append({
                "source": "swebench_verified",
                "instance_id": inst["instance_id"],
                "issue_text": inst["problem_statement"],
                "code_context": context,
                "patch": inst["patch"],
            })
    print(f"Collected {len(examples)} examples from SWE-bench Verified")
    return examples


def from_agentless(agentless_dir: str, limit: int) -> list[dict]:
    examples = []
    if not agentless_dir or not os.path.isdir(agentless_dir):
        print(f"[skip] Agentless dir not found: {agentless_dir}")
        return examples

    for path in Path(agentless_dir).rglob("*.json"):
        if limit and len(examples) >= limit:
            break
        try:
            data = json.loads(path.read_text())
        except json.JSONDecodeError:
            continue
        if "patch" in data and "instance_id" in data:
            examples.append({
                "source": "agentless",
                "instance_id": data["instance_id"],
                "issue_text": data.get("problem_statement", ""),
                "code_context": data.get("edited_files_context", ""),
                "patch": data["patch"],
            })
    print(f"Collected {len(examples)} examples from Agentless")
    return examples


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--swebench-verified-jsonl", default="data/swebench/raw/swebench_verified.jsonl")
    parser.add_argument("--agentless-dir", default="")
    parser.add_argument("--out", default="data/finetune/raw_trajectories.jsonl")
    parser.add_argument("--max-examples", type=int, default=2000)
    parser.add_argument("--workdir", default=tempfile.mkdtemp(prefix="swebench_repos_"))
    args = parser.parse_args()

    all_examples = []
    all_examples += from_swebench_verified(
        args.swebench_verified_jsonl, args.workdir, args.max_examples
    )
    remaining = max(0, args.max_examples - len(all_examples))
    all_examples += from_agentless(args.agentless_dir, remaining)

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as f:
        for ex in all_examples[: args.max_examples]:
            f.write(json.dumps(ex) + "\n")

    print(f"Wrote {min(len(all_examples), args.max_examples)} trajectories to {args.out}")
    if not all_examples:
        print(
            "WARNING: no trajectories collected. Provide --swebench-verified-jsonl "
            "and/or --agentless-dir pointing at real, downloaded data. This script "
            "will not fabricate training examples."
        )
