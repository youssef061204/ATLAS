.PHONY: setup dev test lint build evaluate benchmark benchmark-cv benchmark-tracking benchmark-risk benchmark-forecast benchmark-simulation
setup:
	python -m pip install -e '.[dev]'
	cd frontend && npm ci
	atlas demo --cached
dev:
	python scripts/dev.py
test:
	pytest -q
	cd frontend && npm test
lint:
	ruff check backend scripts
	ruff format --check backend scripts
	cd frontend && npm run lint && npm run typecheck && npm run format:check
build:
	python -m compileall -q backend
	cd frontend && npm run build
evaluate:
	atlas evaluate
	python scripts/export_artifacts.py
benchmark:
	atlas demo
	python scripts/benchmark_streams.py data/demo.mp4
	python scripts/load_test.py
benchmark-cv:
	atlas evaluate --only cv
benchmark-tracking:
	atlas evaluate --only tracking --gt $(GT) --pred $(PRED)
benchmark-risk:
	atlas evaluate --only risk
benchmark-forecast:
	atlas evaluate --only forecast
benchmark-simulation:
	atlas evaluate --only simulation

prepare-real-data:
	python scripts/prepare_real_data.py
evaluate-real-detection evaluate-real-tracking:
	python scripts/evaluate_real.py --only vision --reuse
evaluate-real-forecasting:
	python scripts/evaluate_real.py --only forecast
evaluate-signal-control:
	python scripts/evaluate_real.py --only signal
benchmark-real-video:
	python scripts/evaluate_real.py --only systems
evaluate-real:
	python scripts/evaluate_real.py --reuse
	python scripts/standardize_benchmarks.py
	python scripts/export_artifacts.py
evaluate-all: evaluate evaluate-real
