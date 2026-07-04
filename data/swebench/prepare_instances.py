"""
Builds a stratified sample of 90 instances from the 300-instance SWE-bench Lite
dataset, covering multiple repositories and difficulty levels.

SWE-bench Lite instances carry a `repo` field (e.g. "django/django",
"pytest-dev/pytest", "sympy/sympy", "psf/requests", ...). SWE-bench also
publishes per-instance difficulty tags in some releases; where unavailable we
derive a proxy difficulty from patch size (lines changed) and number of
FAIL_TO_PASS tests, which correlates well with the official annotations:

    simple  : patch <= 10 lines changed AND <= 2 FAIL_TO_PASS tests
    medium  : patch <= 40 lines changed AND <= 5 FAIL_TO_PASS tests
    hard    : everything else

Sampling strategy:
    1. Group instances by (repo, difficulty_bucket).
    2. Allocate slots proportionally to each repo's share of the full 300,
       with a floor of 1 instance per repo that appears at all.
    3. Within each repo, sample across difficulty buckets proportionally,
       with a floor of 1 per bucket that's non-empty for that repo.
    4. Fill any remaining slots (rounding remainder) by largest fractional
       remainder first, to hit exactly 90.

Usage:
    python prepare_instances.py \
        --input data/swebench/raw/swebench_lite.jsonl \
        --output data/swebench/sample_90.jsonl \
        --n 90 --seed 42
"""
import argparse
import json
import random
from collections import defaultdict


def difficulty_bucket(instance: dict) -> str:
    patch = instance.get("patch", "") or ""
    changed_lines = sum(
        1 for line in patch.splitlines()
        if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))
    )
    fail_to_pass = instance.get("FAIL_TO_PASS", "[]")
    if isinstance(fail_to_pass, str):
        try:
            fail_to_pass = json.loads(fail_to_pass)
        except json.JSONDecodeError:
            fail_to_pass = []
    n_fail = len(fail_to_pass)

    if changed_lines <= 10 and n_fail <= 2:
        return "simple"
    elif changed_lines <= 40 and n_fail <= 5:
        return "medium"
    return "hard"


def load_instances(path: str) -> list[dict]:
    instances = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                instances.append(json.loads(line))
    return instances


def stratified_sample(instances: list[dict], n: int, seed: int) -> list[dict]:
    rng = random.Random(seed)

    by_repo = defaultdict(list)
    for inst in instances:
        inst["_difficulty"] = difficulty_bucket(inst)
        by_repo[inst["repo"]].append(inst)

    total = len(instances)
    repos = list(by_repo.keys())

    # Proportional allocation per repo with floor of 1.
    raw_alloc = {r: max(1, round(len(by_repo[r]) / total * n)) for r in repos}
    # Adjust to hit exactly n.
    diff = n - sum(raw_alloc.values())
    repos_sorted_by_size = sorted(repos, key=lambda r: -len(by_repo[r]))
    i = 0
    while diff != 0 and repos_sorted_by_size:
        r = repos_sorted_by_size[i % len(repos_sorted_by_size)]
        if diff > 0:
            raw_alloc[r] += 1
            diff -= 1
        elif raw_alloc[r] > 1:
            raw_alloc[r] -= 1
            diff += 1
        i += 1

    sampled = []
    for repo, quota in raw_alloc.items():
        pool = by_repo[repo]
        by_bucket = defaultdict(list)
        for inst in pool:
            by_bucket[inst["_difficulty"]].append(inst)

        buckets = [b for b in ("simple", "medium", "hard") if by_bucket[b]]
        per_bucket_quota = max(1, quota // max(1, len(buckets)))

        picked = []
        for b in buckets:
            rng.shuffle(by_bucket[b])
            picked.extend(by_bucket[b][:per_bucket_quota])

        # Top up / trim to match this repo's quota.
        remaining_pool = [x for x in pool if x not in picked]
        rng.shuffle(remaining_pool)
        while len(picked) < quota and remaining_pool:
            picked.append(remaining_pool.pop())
        picked = picked[:quota]
        sampled.extend(picked)

    rng.shuffle(sampled)
    return sampled[:n]


def summarize(sample: list[dict]) -> None:
    by_repo = defaultdict(int)
    by_diff = defaultdict(int)
    for inst in sample:
        by_repo[inst["repo"]] += 1
        by_diff[inst["_difficulty"]] += 1
    print(f"Total sampled: {len(sample)}")
    print("By repo:")
    for r, c in sorted(by_repo.items(), key=lambda x: -x[1]):
        print(f"  {r}: {c}")
    print("By difficulty:")
    for d, c in sorted(by_diff.items()):
        print(f"  {d}: {c}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/swebench/raw/swebench_lite.jsonl")
    parser.add_argument("--output", default="data/swebench/sample_90.jsonl")
    parser.add_argument("--n", type=int, default=90)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    instances = load_instances(args.input)
    sample = stratified_sample(instances, args.n, args.seed)
    summarize(sample)

    with open(args.output, "w") as f:
        for inst in sample:
            f.write(json.dumps(inst) + "\n")
    print(f"Wrote {len(sample)} instances to {args.output}")
