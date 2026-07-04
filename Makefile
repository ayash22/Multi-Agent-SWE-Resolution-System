.PHONY: install install-frontend lint test test-unit test-integration \
        run-backend run-frontend docker-up docker-down \
        download-data prepare-sample train-ranker \
        eval-baseline eval-full-system eval-report clean

# --- Setup ---
install:
	pip install -r requirements.txt

install-frontend:
	cd frontend && npm install

# --- Quality gates (mirrors .github/workflows/ci.yml) ---
lint:
	ruff check .

test-unit:
	pytest tests/ -v --ignore=tests/test_docker_sandbox_integration.py

test-integration:
	pytest tests/test_docker_sandbox_integration.py -v

test: lint test-unit test-integration

# --- Local dev servers ---
run-backend:
	uvicorn serving.app.main:app --reload --port 8000

run-frontend:
	cd frontend && npm run dev

docker-up:
	docker-compose up -d

docker-down:
	docker-compose down

# --- Data pipeline ---
download-data:
	python data/swebench/download_swebench.py --out data/swebench/raw

prepare-sample:
	python data/swebench/prepare_instances.py \
		--input data/swebench/raw/swebench_lite.jsonl \
		--output data/swebench/sample_90.jsonl

train-ranker:
	python patch_ranking/patch_ranker_model.py evaluation/labeled_examples.jsonl

# --- Evaluation (requires OPENAI_API_KEY + Docker; see README) ---
eval-baseline:
	python evaluation/run_swebench_eval.py generate \
		--instances data/swebench/sample_90.jsonl --config baseline \
		--out evaluation/predictions/baseline.jsonl
	python evaluation/run_swebench_eval.py grade \
		--predictions evaluation/predictions/baseline.jsonl --run-id baseline_run

eval-full-system:
	python evaluation/run_swebench_eval.py generate \
		--instances data/swebench/sample_90.jsonl --config full_system \
		--out evaluation/predictions/full_system.jsonl
	python evaluation/run_swebench_eval.py grade \
		--predictions evaluation/predictions/full_system.jsonl --run-id full_system_run

eval-report:
	python evaluation/run_swebench_eval.py report \
		--baseline-results logs/run_evaluation/baseline_run \
		--full-system-results logs/run_evaluation/full_system_run \
		--out evaluation/eval_report.md

clean:
	find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete
	rm -rf .pytest_cache .ruff_cache frontend/dist frontend/node_modules
