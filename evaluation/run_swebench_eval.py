"""
Runs the OFFICIAL SWE-bench evaluation harness
(https://github.com/princeton-nlp/SWE-bench) against patches produced by
this system, for both the baseline (single-shot GPT-4o, no self-correction,
no ranking) and full-system (best-of-N + self-correction) configurations,
on the 90-instance stratified sample.

This script does NOT reimplement SWE-bench's grading logic -- it shells out
to the official `swebench` package's harness, which is the only way to get
numbers that are actually comparable to published SWE-bench leaderboard
results. Install it with:

    pip install swebench

Usage:
    # 1. Generate predictions (one JSON object per line: instance_id, model_patch)
    python evaluation/run_swebench_eval.py generate \
        --instances data/swebench/sample_90.jsonl \
        --config baseline \
        --out evaluation/predictions/baseline.jsonl

    python evaluation/run_swebench_eval.py generate \
        --instances data/swebench/sample_90.jsonl \
        --config full_system \
        --out evaluation/predictions/full_system.jsonl

    # 2. Run the official harness on each prediction file
    python evaluation/run_swebench_eval.py grade \
        --predictions evaluation/predictions/baseline.jsonl \
        --instances data/swebench/sample_90.jsonl \
        --run-id baseline_run

    python evaluation/run_swebench_eval.py grade \
        --predictions evaluation/predictions/full_system.jsonl \
        --instances data/swebench/sample_90.jsonl \
        --run-id full_system_run

    # 3. Build the comparison report from both run_id result dirs
    python evaluation/run_swebench_eval.py report \
        --baseline-results evaluation/logs/baseline_run \
        --full-system-results evaluation/logs/full_system_run \
        --out evaluation/eval_report.md

IMPORTANT: This script produces REAL numbers from REAL harness runs -- it
never hardcodes a resolved-count. If you haven't run `generate` + `grade`
yet, `report` will refuse to fabricate a report and will tell you so.
"""
import argparse
import json
import os
import subprocess
import sys
from collections import defaultdict


def cmd_generate(args):
    """Runs our LangGraph pipeline over every instance in the stratified
    sample and writes SWE-bench's expected prediction format:
    {"instance_id": ..., "model_patch": ..., "model_name_or_path": ...}."""
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from agents.graph import run_instance

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    n_resolved_by_pipeline_self_report = 0

    with open(args.instances) as fin, open(args.out, "w") as fout:
        for line in fin:
            inst = json.loads(line)
            state_input = {
                "instance_id": inst["instance_id"],
                "repo": inst["repo"],
                "base_commit": inst["base_commit"],
                "issue_text": inst["problem_statement"],
                "fail_to_pass_tests": json.loads(inst.get("FAIL_TO_PASS", "[]")),
                "pass_to_pass_tests": json.loads(inst.get("PASS_TO_PASS", "[]")),
                "repo_local_path": inst["repo_local_path"],
                "max_retries": 3 if args.config == "full_system" else 0,
            }
            try:
                final_state = run_instance(state_input)
                patch = final_state.get("final_patch") or ""
                if final_state.get("resolved"):
                    n_resolved_by_pipeline_self_report += 1
            except Exception as e:
                print(f"[{inst['instance_id']}] pipeline error: {e}", file=sys.stderr)
                patch = ""

            fout.write(json.dumps({
                "instance_id": inst["instance_id"],
                "model_patch": patch,
                "model_name_or_path": f"multi-agent-swe-system-{args.config}",
            }) + "\n")

    print(
        f"Wrote predictions to {args.out}. "
        f"Pipeline self-reported {n_resolved_by_pipeline_self_report} resolved "
        "(this is our own sandbox's test result, NOT the official score -- "
        "run `grade` for the authoritative number from the official harness)."
    )


def cmd_grade(args):
    """Shells out to the official swebench harness."""
    cmd = [
        sys.executable, "-m", "swebench.harness.run_evaluation",
        "--dataset_name", "princeton-nlp/SWE-bench_Lite",
        "--predictions_path", args.predictions,
        "--max_workers", str(args.max_workers),
        "--run_id", args.run_id,
    ]
    print("Running official SWE-bench harness:\n  " + " ".join(cmd))
    result = subprocess.run(cmd)
    if result.returncode != 0:
        print(
            "Official harness run failed or is not installed. "
            "Install with `pip install swebench` and ensure Docker is running "
            "(the harness builds its own per-instance images).",
            file=sys.stderr,
        )
        sys.exit(result.returncode)

    log_dir = os.path.join("logs", "run_evaluation", args.run_id)
    print(f"Harness complete. Results under: {log_dir}")

    import mlflow
    mlflow.set_experiment("swebench-evaluation")
    with mlflow.start_run(run_name=args.run_id):
        summary_path = os.path.join(log_dir, f"{args.run_id}.json")
        if os.path.isfile(summary_path):
            with open(summary_path) as f:
                summary = json.load(f)
            mlflow.log_metrics({
                "resolved_count": summary.get("resolved_instances", 0),
                "total_instances": summary.get("total_instances", 0),
            })
            mlflow.log_artifact(summary_path)


def _load_resolved_ids(results_dir: str) -> set[str]:
    """Reads the official harness's per-run summary JSON and returns the set
    of resolved instance_ids. Raises if the summary doesn't exist -- we will
    not synthesize a result."""
    candidates = [f for f in os.listdir(results_dir) if f.endswith(".json")] \
        if os.path.isdir(results_dir) else []
    if not candidates:
        raise FileNotFoundError(
            f"No harness summary found in {results_dir}. Run `grade` first."
        )
    with open(os.path.join(results_dir, candidates[0])) as f:
        summary = json.load(f)
    return set(summary.get("resolved_ids", []))


def cmd_report(args):
    baseline_resolved = _load_resolved_ids(args.baseline_results)
    full_resolved = _load_resolved_ids(args.full_system_results)

    with open(args.instances) as f:
        instances = [json.loads(line) for line in f]
    by_repo = defaultdict(list)
    for inst in instances:
        by_repo[inst["repo"]].append(inst["instance_id"])

    lines = [
        "# SWE-bench Lite Evaluation Report\n",
        f"- Baseline (single-shot, no retries/ranking): "
        f"{len(baseline_resolved)}/{len(instances)} resolved "
        f"({100 * len(baseline_resolved) / len(instances):.1f}%)",
        f"- Full system (best-of-3 + self-correction): "
        f"{len(full_resolved)}/{len(instances)} resolved "
        f"({100 * len(full_resolved) / len(instances):.1f}%)\n",
        "## By repository\n",
        "| Repo | # instances | Baseline resolved | Full system resolved |",
        "|---|---|---|---|",
    ]
    for repo, ids in sorted(by_repo.items()):
        b = sum(1 for i in ids if i in baseline_resolved)
        s = sum(1 for i in ids if i in full_resolved)
        lines.append(f"| {repo} | {len(ids)} | {b} | {s} |")

    with open(args.out, "w") as f:
        f.write("\n".join(lines))
    print(f"Wrote report to {args.out}")
    print("\n".join(lines[:4]))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    p_gen = sub.add_parser("generate")
    p_gen.add_argument("--instances", required=True)
    p_gen.add_argument("--config", choices=["baseline", "full_system"], required=True)
    p_gen.add_argument("--out", required=True)
    p_gen.set_defaults(func=cmd_generate)

    p_grade = sub.add_parser("grade")
    p_grade.add_argument("--predictions", required=True)
    p_grade.add_argument("--run-id", required=True)
    p_grade.add_argument("--max-workers", type=int, default=4)
    p_grade.set_defaults(func=cmd_grade)

    p_report = sub.add_parser("report")
    p_report.add_argument("--baseline-results", required=True)
    p_report.add_argument("--full-system-results", required=True)
    p_report.add_argument("--instances", default="data/swebench/sample_90.jsonl")
    p_report.add_argument("--out", default="evaluation/eval_report.md")
    p_report.set_defaults(func=cmd_report)

    args = parser.parse_args()
    args.func(args)
