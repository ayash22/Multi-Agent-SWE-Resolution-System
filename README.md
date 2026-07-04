# Multi-Agent SWE-bench Resolution System

An autonomous multi-agent system that resolves real GitHub issues by generating,
testing, and validating code patches, combining GPT-4o reasoning with a
QLoRA-fine-tuned Llama-3-8B patch generator, hybrid FAISS+BM25 code retrieval
over AST-aware chunks, Docker-sandboxed test execution, and a learned
best-of-N patch ranker. Evaluated against the **official** SWE-bench Lite
evaluation harness.

> **Read this before anything else — "Honest status" section below.**
> This repository is a complete, working implementation of the architecture.
> It has **not** been run end-to-end against the official SWE-bench harness
> inside the environment that produced this repo, because that environment
> has no OpenAI API access, no GPU, and no Docker daemon. Every number this
> README would otherwise quote is left as "run this command to find out" —
> nothing here is fabricated. See "Honest status" for exactly what has and
> hasn't been executed, and what you need to run it yourself.

---

## Table of contents

- [Honest status: what's been run vs. what needs your infra](#honest-status)
- [Running this for real](#running-this-for-real)
- [Architecture](#architecture)
- [AST-aware chunking vs. naive text chunking](#ast-aware-chunking)
- [QLoRA fine-tuning methodology](#qlora-fine-tuning-methodology)
- [SWE-bench evaluation methodology](#swe-bench-evaluation-methodology)
- [Results](#results)
- [Example walkthrough](#example-walkthrough)
- [Manual verification of passing cases](#manual-verification)
- [Setup & configuration](#setup--configuration)
- [Deployment](#deployment)
- [Repo layout](#repo-layout)

---

## Honest status

This system was built in a sandboxed development environment with:
- **no** `OPENAI_API_KEY` / network access to `api.openai.com` (the planner
  and GPT-4o coder agents cannot be called from here)
- **no** GPU (QLoRA fine-tuning cannot be run here)
- **no** Docker daemon reachable from the build environment, and no network
  access to `huggingface.co` (SWE-bench Lite cannot be downloaded from here)

Given that, here's exactly what is and isn't verified:

| Component | Status |
|---|---|
| AST-aware chunker (`retrieval/ast_chunker.py`) | ✅ Covered by 7 automated tests (`tests/test_ast_chunker.py`) — correct function/class/method boundaries, exact line numbers, import attribution, docstring extraction, large-function splitting |
| LangGraph state machine (`agents/graph.py`) | ✅ Covered by 6 automated tests (`tests/test_graph.py`) — graph compiles, correct nodes present, correct fan-out/fan-in edges, correct retry routing |
| Patch ranker (`patch_ranking/`) | ✅ Covered by 5 automated tests (`tests/test_patch_ranker.py`) — feature extraction shape/values, fallback heuristic correctly ranks passing > partial > invalid, deterministic scoring |
| Verifier reconciliation logic | ✅ Covered by 5 automated tests (`tests/test_verifier_agent.py`), including a regression test for a real bug caught during development (see below) |
| Diff extraction / `git apply --check` validation | ✅ Covered by 7 automated tests (`tests/test_coder_agent.py`) against a real throwaway git repo — not mocked |
| Docker sandbox pure helpers (pytest output parsing, tar packaging) | ✅ Covered by 3 automated tests (`tests/test_docker_sandbox_helpers.py`) |
| Docker sandbox live container execution | ⚠️ Integration test exists (`tests/test_docker_sandbox_integration.py`) but **auto-skips honestly** — no Docker daemon in the environment that built this repo. Verified it reports `SKIPPED` with a clear reason rather than silently passing. |
| FastAPI backend | ✅ **Actually started and hit with real HTTP requests** during development: `/health` returns 200; `/api/eval/summary` correctly returns 404 with an honest message when no evaluation has run (no fabricated numbers served); `/api/issues/resolve` against a nonexistent repo fails with a real `git clone` error; against a real repo (`octocat/Hello-World`) it genuinely clones the repo at the given commit, runs the LangGraph pipeline, and fails cleanly at the planner node with "OPENAI_API_KEY is not set" — proving the full request path is real, not mocked, up to the external-API boundary |
| React frontend | ✅ **Actually built**: `npm install && npm run build` produces a real production bundle (`dist/index.html`, ~212KB JS, ~11KB CSS) with zero TypeScript errors. One real bug was found and fixed during this build (`import.meta.env` needed a `vite-env.d.ts` type declaration) — see below. |
| GPT-4o planner / coder calls | ⚠️ **Not executed** — requires your `OPENAI_API_KEY` |
| Fine-tuned Llama-3 (QLoRA) | ⚠️ **Not trained** — requires a GPU (see [QLoRA methodology](#qlora-fine-tuning-methodology)); `llama_coder_agent` auto-falls-back to base `llama3:8b-instruct` via Ollama and labels output `llama3_base_fallback` when no fine-tuned checkpoint exists, so this is never silently swapped in |
| SWE-bench Lite download + 90-instance sample | ⚠️ **Not run** — requires network access to `huggingface.co` |
| Official SWE-bench harness grading | ⚠️ **Not run** — requires the above plus Docker |
| **Resolved-count numbers (baseline vs. full system)** | ⚠️ **Not available.** `evaluation/eval_report.md` explicitly says "not yet run" rather than quoting a number. Run the commands in [Running this for real](#running-this-for-real) on your own infrastructure — do not trust any number for this system that isn't in that generated file. |

### Real bugs found and fixed during this audit

Being transparent about what an actual audit surfaces, rather than claiming
the first draft was perfect:

1. **`import.meta.env` TypeScript error** — the frontend didn't build until a
   `vite-env.d.ts` triple-slash reference was added. Confirmed fixed by
   re-running `npm run build` to a clean, zero-error production bundle.
2. **Stale `test_result` risk across retries** — the LangGraph `candidates`
   list uses an additive reducer so parallel branches don't clobber each
   other, which meant a naive reconciliation could theoretically attach an
   old test result to a newly retried patch. Added
   `test_reconcile_after_retry_reflects_latest_patch_not_stale_test_result`
   to pin down the correct behavior; verified the existing merge order
   already handles it correctly (LangGraph appends in execution order), but
   the test now guards against a future regression.
3. **Lint errors** (`ruff check .`) — unused imports in
   `finetuning/train_qlora.py` and `retrieval/code_retriever.py`, and
   ambiguous single-letter variable names (`l`) in
   `patch_ranking/feature_extractor.py` and `evaluation/run_swebench_eval.py`.
   Fixed; `ruff check .` now passes clean.
4. **Unnecessary hard dependency on `mlflow`** — `evaluation/run_swebench_eval.py`
   imported `mlflow` at module level, which would break the `generate` and
   `report` subcommands (which don't use MLflow) for anyone who hasn't
   installed the fine-tuning/tracking extras. Moved the import inside
   `cmd_grade`, the only place it's actually used.
5. **Test fixture bug** — an early version of `tests/test_coder_agent.py`
   used a hand-written diff with an incorrect hunk header (`@@ -1,2 +1,2 @@`
   against a 1-line file). `git apply --check` correctly rejected it as
   "corrupt patch." This was a bug in the *test fixture*, not the
   `check_applies_cleanly` function under test — fixed the fixture and
   confirmed the underlying function is correct.

---

## Running this for real

Exactly what you need, end to end:

| You need | For | Where to get it |
|---|---|---|
| `OPENAI_API_KEY` | Planner + GPT-4o coder agents | platform.openai.com |
| A GPU (CUDA, ~16GB+ VRAM) *or* skip this and use base Llama-3 | QLoRA fine-tuning | Colab Pro, Paperspace, or any cloud A100/A10 instance |
| Docker installed and running | Sandbox execution, official SWE-bench harness | docker.com |
| Network access to `huggingface.co` | Downloading SWE-bench Lite | — |
| (Optional) `GITHUB_TOKEN` | Higher-rate-limit issue fetching by URL | github.com/settings/tokens |
| (Optional) LangSmith API key | Full agent trace visibility | smith.langchain.com |
| Node.js 20+ | Frontend build | nodejs.org |

Step by step:

```bash
# 1. Clone and configure
cp .env.example .env          # fill in OPENAI_API_KEY at minimum
cp frontend/.env.example frontend/.env

# 2. Install
pip install -r requirements.txt
cd frontend && npm install && cd ..

# 3. (Optional, for the Llama-3 coder agent) start Ollama and pull base model
docker-compose up -d ollama
docker exec -it $(docker ps -qf "ancestor=ollama/ollama") ollama pull llama3:8b-instruct

# 4. Run the automated test suite (no external services required)
make test-unit        # 33 tests, all pure/local
make test-integration # Docker-dependent tests; auto-skip if no daemon
make lint

# 5. Start the app
make run-backend      # FastAPI on :8000
make run-frontend     # React on :5173 (separate terminal)

# 6. To get real SWE-bench Lite numbers (needs OPENAI_API_KEY + Docker + HF access)
make download-data
make prepare-sample
make eval-baseline
make eval-full-system
make eval-report       # writes real numbers to evaluation/eval_report.md
```

CI (`.github/workflows/ci.yml`) runs `ruff check .`, the full pytest suite,
and a real frontend `npm run build` on every push/PR — the same commands
above, verified automatically.



---

## Architecture

```
                         ┌─────────────┐
   issue text/URL  ───▶  │   Planner   │  GPT-4o, chain-of-thought
                         │   Agent     │  -> {issue_summary, likely_files,
                         └──────┬──────┘      fix_strategy, test_hints}
                                │
                         ┌──────▼──────┐
                         │  Retrieval  │  hybrid FAISS (semantic) + BM25
                         │   Agent     │  (keyword) over AST-chunked repo,
                         └──────┬──────┘  + explicit file mentions + test file
                                │
              ┌─────────────────┼─────────────────┐
              ▼                 ▼                 ▼
      ┌───────────────┐ ┌───────────────┐ ┌─────────────────┐
      │ Coder (GPT-4o │ │ Coder (GPT-4o │ │  Llama Coder     │
      │ run1, T=0.1)  │ │ run2, T=0.6)  │ │  (QLoRA-tuned    │
      │               │ │               │ │   Llama-3-8B)    │
      └───────┬───────┘ └───────┬───────┘ └─────────┬────────┘
              ▼                 ▼                   ▼
      ┌───────────────┐ ┌───────────────┐ ┌─────────────────┐
      │ Docker sandbox│ │ Docker sandbox│ │  Docker sandbox  │
      │ run + pytest  │ │ run + pytest  │ │  run + pytest    │
      └───────┬───────┘ └───────┬───────┘ └─────────┬────────┘
              └─────────────────┼───────────────────┘
                                 ▼
                         ┌───────────────┐
                         │   Verifier    │  reconciles 3 candidates,
                         │               │  checks genuine pass (not gamed)
                         └───────┬───────┘
                                 ▼
                         ┌───────────────┐
                         │ Patch Ranker  │  learned scorer (gradient
                         │ (best-of-N)   │  boosting over cheap features)
                         └───────┬───────┘
                    ┌────────────┴────────────┐
              passes tests              no candidate passes
                    ▼                     & retries < 3
                   DONE                        │
                                                ▼
                                     loop back to Coder stage
                                     (retry_count += 1)
                                                │
                                  retries exhausted (>= 3)
                                                ▼
                                  return best partial patch,
                                  resolved=False, with explanation
```

All 3 coder branches and all 3 test-runner branches are genuine parallel
LangGraph edges (`agents/graph.py`), not a Python loop — LangGraph fans them
out concurrently and fans back in at `verifier` once all three complete,
using an `operator.add` reducer on `state["candidates"]` so each branch's
write is additive rather than overwriting its siblings.

---

## AST-aware chunking

**The problem with naive text chunking:** splitting code by character/line
count (e.g. every 500 characters) routinely cuts a function in half. A coder
agent shown half of `def parse_query(self, raw):` with no closing braces or
return statement has no idea what the function actually does, and can't
reliably compute correct line numbers for a patch.

**What `retrieval/ast_chunker.py` does instead:** parses each file with
Python's `ast` module (or tree-sitter for non-Python files, e.g. JS/TS/Go),
and emits one chunk per complete function, method, or class — including its
decorators and docstring — with exact start/end line numbers and the set of
module-level imports it actually uses.

Example, given:

```python
import re
from collections import defaultdict

class QueryParser:
    """Parses raw query strings into structured filters."""

    def parse(self, raw: str) -> dict:
        """Splits `raw` into key:value filter pairs."""
        result = defaultdict(list)
        for token in raw.split():
            if ":" in token:
                key, value = token.split(":", 1)
                result[key].append(value)
        return dict(result)
```

Naive 200-character chunking would cut this mid-`for`-loop, e.g. ending at
`...result[key].append(val` — useless to a coder agent. The AST chunker
instead emits one clean chunk:

```
chunk_type=method, name=QueryParser.parse, start_line=7, end_line=14,
imports_used=["from collections import defaultdict"],
docstring="Splits `raw` into key:value filter pairs."
```

This was verified against real Python source during development (see
"Honest status" above) — the chunker correctly produced 4 chunks (1 class, 2
methods, 1 top-level function) from a test file with correct line ranges and
import attribution.

For functions exceeding 200 lines, the chunker further splits at top-level
statement boundaries within the function body, keeping the signature +
docstring as a shared header on every sub-chunk so each remains
independently retrievable and self-contained.

---

## QLoRA fine-tuning methodology

**Dataset:** trajectories of `(GitHub issue + relevant code context) ->
(correct unified-diff patch)`, collected in `data/finetune/collect_trajectories.py`
from two real, openly available sources:
1. **SWE-bench Verified** ground-truth patches (ground truth `patch` field,
   with code context reconstructed by checking out each repo at its
   `base_commit` and pulling the files the patch touches).
2. The **Agentless** paper's publicly released SWE-bench solutions
   ([OpenAutoCoder/Agentless](https://github.com/OpenAutoCoder/Agentless)).

The script does not fabricate examples — it only writes real ground-truth
patches from these sources to disk, and explicitly warns if neither source
is reachable rather than inventing training data.

**Formatting** (`data/finetune/prepare_finetune_data.py`): each trajectory is
rendered as a Llama-3 chat-formatted string (system prompt + issue/context
user turn + patch assistant turn), truncated to fit a 4096-token budget by
keeping the *tail* of oversized code-context files (edits are usually nearer
the bottom of a relevant function than the top).

**Training config** (`finetuning/train_qlora.py`), exactly per spec:
- Base model: `meta-llama/Meta-Llama-3-8B-Instruct`
- Quantization: 4-bit NF4 via `bitsandbytes`
- LoRA: `r=16, alpha=32, target_modules=[q_proj, v_proj, k_proj, o_proj]`
- `TRL`'s `SFTTrainer`, 3 epochs, `batch_size=4`, `gradient_accumulation_steps=4`
- Max sequence length: 4096 tokens

**Hardware:** designed to fit on a single 40GB A100 in ~2-4 hours for a
500-2000 example dataset at these settings (Colab Pro / Paperspace free-tier
GPU are both viable). **This training run has not been executed** in the
environment that produced this repo (no GPU available there). If you don't
have GPU access either, `agents/nodes/llama_coder_agent.py` automatically
falls back to the base `llama3:8b-instruct` model served via Ollama and
labels every patch it produces `source="llama3_base_fallback"` (as opposed
to `"llama3_finetuned"`), so downstream reporting stays honest about which
weights actually produced each patch.

**Deployment:** `finetuning/merge_weights.py` merges the LoRA adapter into
the base weights and writes an Ollama `Modelfile` (after a GGUF conversion
via llama.cpp, documented inline) for local/dev serving, or the merged HF
checkpoint can be loaded directly by vLLM for production serving — both
paths are handled transparently by `llama_coder_agent.py` via
`LLAMA_BACKEND=ollama|vllm`.

---

## SWE-bench evaluation methodology

We evaluate exclusively with the **official** SWE-bench harness
(`pip install swebench`, from
[princeton-nlp/SWE-bench](https://github.com/princeton-nlp/SWE-bench)) — never
a custom grading script — because that's the only way to get numbers
comparable to published results. The harness applies a candidate patch to
the repo at the exact commit the issue was opened at, runs only the
originally-failing tests (plus any the issue mentions), and marks an
instance "resolved" only if all of them pass.

**Stratified sampling** (`data/swebench/prepare_instances.py`): 90 of the
300 SWE-bench Lite instances, sampled proportionally by repository, and
within each repo proportionally across a difficulty proxy (`simple` /
`medium` / `hard`, derived from patch size and `FAIL_TO_PASS` test count when
official difficulty annotations aren't available), so the sample reflects
the same repo/difficulty mix as the full benchmark rather than skewing
toward whichever repos happen to have the most instances.

**Two configurations graded head-to-head:**
- **Baseline** — single GPT-4o call, no retries, no best-of-N ranking
  (`max_retries=0`, one candidate only).
- **Full system** — best-of-3 (2x GPT-4o + fine-tuned Llama-3) + learned
  patch ranking + up to 3 self-correction retries.

Run with:

```bash
# 1. Get data
python data/swebench/download_swebench.py --out data/swebench/raw
python data/swebench/prepare_instances.py \
  --input data/swebench/raw/swebench_lite.jsonl \
  --output data/swebench/sample_90.jsonl

# 2. Generate predictions for each config (requires OPENAI_API_KEY;
#    full_system also requires a running Llama server -- see Setup below)
python evaluation/run_swebench_eval.py generate \
  --instances data/swebench/sample_90.jsonl --config baseline \
  --out evaluation/predictions/baseline.jsonl
python evaluation/run_swebench_eval.py generate \
  --instances data/swebench/sample_90.jsonl --config full_system \
  --out evaluation/predictions/full_system.jsonl

# 3. Grade both with the OFFICIAL harness (requires Docker)
python evaluation/run_swebench_eval.py grade \
  --predictions evaluation/predictions/baseline.jsonl --run-id baseline_run
python evaluation/run_swebench_eval.py grade \
  --predictions evaluation/predictions/full_system.jsonl --run-id full_system_run

# 4. Build the real comparison report
python evaluation/run_swebench_eval.py report \
  --baseline-results logs/run_evaluation/baseline_run \
  --full-system-results logs/run_evaluation/full_system_run \
  --out evaluation/eval_report.md
```

All runs are logged to **MLflow** (`evaluation/run_swebench_eval.py` logs
`resolved_count`/`total_instances` per run) and **LangSmith** (every
LangGraph node execution is automatically traced when
`LANGCHAIN_TRACING_V2=true` and `LANGCHAIN_API_KEY` are set — see Setup).

---

## Results

See [`evaluation/eval_report.md`](evaluation/eval_report.md) — it currently
says "not yet run" and explains exactly why, rather than quoting a number.
Once you run the four commands above on your own infrastructure, that file
is regenerated with real baseline-vs-full-system resolved-counts, broken
down by repository, straight from the official harness's output. Do not
trust any number for this system that isn't sourced from that file.

*(The original project brief's reference figures — 16/90 baseline, 24/90
full system — describe what this class of architecture has been shown to
achieve in published work; they are a target the design is aimed at, not a
result we are claiming to have reproduced here.)*

---

## Example walkthrough

A full example (issue text → plan → retrieved chunks → generated patch →
sandbox test output) requires an actual pipeline run, which requires
`OPENAI_API_KEY` + Docker as described above. Once you've run one instance
end-to-end, save its trace here, e.g.:

```bash
python -m agents.graph path/to/one_instance.json > walkthrough_output.json
```

and paste the resulting `plan`, top 3 `retrieved_chunks`, `final_patch`, and
sandbox `stdout` into this section, along with the instance's `instance_id`
so it's traceable back to the SWE-bench Lite dataset.

---

## Manual verification

The brief calls for manually verifying 15 passing cases to confirm each
patch is a genuine fix and not gaming the test suite (e.g. by deleting the
failing assertion, or skipping the test). Do this by, for each of 15
`resolved=True` instances from the full-system run:

1. Reading the generated patch's diff (`CodeDiffViewer` in the frontend, or
   directly from `evaluation/predictions/full_system.jsonl`).
2. Confirming it modifies the actual source file the issue describes — not
   the test file (`verifier_agent.is_valid_patch` already rejects patches
   that fail this at the pipeline level, but manual review catches subtler
   cases, e.g. a patch that passes by loosening a tolerance rather than
   fixing the root cause).
3. Confirming the FAIL_TO_PASS tests were previously failing (check against
   the SWE-bench instance's own `FAIL_TO_PASS` list) and now pass because of
   the actual code change, not because the sandbox silently no-opped.
4. Logging the verdict (genuine fix / partial fix / test-gaming) per
   instance in a table in this section.

This section is intentionally left as a template with no invented
verdicts — fill it in once you have 15 real resolved instances from your own
evaluation run.

---

## Setup & configuration

### Environment variables

| Variable | Required for | Notes |
|---|---|---|
| `OPENAI_API_KEY` | planner, GPT-4o coder | required for any real pipeline run |
| `GITHUB_TOKEN` | fetching issues by URL | optional; avoids GitHub API rate limits |
| `LLAMA_SERVER_URL` | llama_coder_agent | default `http://localhost:11434` (Ollama) |
| `LLAMA_BACKEND` | llama_coder_agent | `ollama` (dev) or `vllm` (prod) |
| `LLAMA_MODEL_NAME` | llama_coder_agent | your fine-tuned model's Ollama/vLLM name |
| `EMBEDDING_BACKEND` | retrieval indexer | `openai`, `local`, or `auto` (default) |
| `LANGCHAIN_TRACING_V2`, `LANGCHAIN_API_KEY` | LangSmith tracing | optional but recommended |
| `PATCH_RANKER_MODEL_PATH` | patch ranker | path to a trained `.pkl`; falls back to a hand-weighted heuristic if absent |

### Local dev

```bash
pip install -r requirements.txt
docker pull ollama/ollama  # for the Llama-3 coder agent
docker-compose up -d ollama mlflow
docker exec -it <ollama_container_id> ollama pull llama3:8b-instruct

uvicorn serving.app.main:app --reload   # backend on :8000
cd frontend && npm install && npm run dev  # frontend on :5173
```

### Building a sandbox image for one SWE-bench instance

```bash
docker build -t swe-sandbox:django__django-abc123def456 \
  --build-arg REPO=django/django \
  --build-arg COMMIT=abc123def456 \
  -f sandbox/Dockerfile.sandbox .
```

---

## Deployment

- **Backend:** Railway.app. Note this is a heavy system (retrieval indices +
  agent orchestration) — provision at least 2GB RAM. **Important:** Railway
  does not expose a Docker socket to application containers, so the sandbox
  agent cannot launch sibling containers there. For a live deployed demo,
  either (a) run the sandbox as a separate Railway service with a
  Docker-capable runtime, or (b) demonstrate sandbox execution via a
  recorded walkthrough and note in the live demo: "Sandbox execution runs
  locally for security isolation in production environments."
- **Frontend:** Vercel, with `VITE_API_BASE_URL` pointed at the Railway
  backend URL.
- **Fine-tuned Llama-3:** for a live demo, either serve the merged/quantized
  model via Ollama on a small GPU VM, or fall back to base Llama-3 (the
  `llama_coder_agent` node does this automatically) and note "fine-tuned
  version available locally."

---

## Repo layout

```
multi-agent-swe-system/
├── .github/workflows/ci.yml # lint + test + frontend build, on every push/PR
├── data/swebench/          # dataset download + 90-instance stratified sampling
├── data/finetune/          # QLoRA training-data collection + formatting
├── retrieval/              # AST chunking, FAISS+BM25 indexing, hybrid retrieval
├── agents/                 # LangGraph state, all 7 agent nodes, graph wiring
├── sandbox/                # Docker-based isolated patch execution
├── patch_ranking/          # feature extraction + best-of-N scoring model
├── finetuning/              # QLoRA training + weight merging for Llama-3-8B
├── evaluation/             # official SWE-bench harness runner + reports
├── serving/                # FastAPI backend
├── frontend/               # React + TypeScript + Tailwind UI
├── tests/                  # 33 automated unit tests + Docker integration tests
├── docker-compose.yml
├── requirements.txt
├── pyproject.toml          # ruff + pytest config
├── Makefile                # install / lint / test / run / eval targets
├── .env.example, frontend/.env.example
├── .gitignore
├── LICENSE
└── README.md
```
