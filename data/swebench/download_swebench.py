"""
Downloads the SWE-bench Lite dataset (300 instances) from HuggingFace.

Dataset: princeton-nlp/SWE-bench_Lite
https://huggingface.co/datasets/princeton-nlp/SWE-bench_Lite

Requires: `pip install datasets huggingface_hub`
Requires network access to huggingface.co (not available in every sandboxed
environment -- if this fails, download manually and place the resulting
jsonl at data/swebench/raw/swebench_lite.jsonl).

Usage:
    python download_swebench.py --out data/swebench/raw
"""
import argparse
import json
import os
import sys


def download(out_dir: str) -> str:
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "swebench_lite.jsonl")

    try:
        from datasets import load_dataset
    except ImportError:
        print(
            "The `datasets` package is required. Install with "
            "`pip install datasets huggingface_hub`.",
            file=sys.stderr,
        )
        sys.exit(1)

    print("Downloading princeton-nlp/SWE-bench_Lite (test split) ...")
    try:
        ds = load_dataset("princeton-nlp/SWE-bench_Lite", split="test")
    except Exception as e:
        print(
            f"Failed to download dataset from HuggingFace: {e}\n"
            "This usually means there is no network access to huggingface.co "
            "from this environment. Download the dataset separately (e.g. from "
            "a machine with internet access, or via the HF CLI) and place the "
            f"file at {out_path} as line-delimited JSON, one instance per line, "
            "with the SWE-bench schema (instance_id, repo, base_commit, "
            "problem_statement, patch, test_patch, FAIL_TO_PASS, PASS_TO_PASS, "
            "version).",
            file=sys.stderr,
        )
        sys.exit(1)

    with open(out_path, "w") as f:
        for row in ds:
            f.write(json.dumps(row) + "\n")

    print(f"Wrote {len(ds)} instances to {out_path}")
    return out_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="data/swebench/raw")
    args = parser.parse_args()
    download(args.out)
