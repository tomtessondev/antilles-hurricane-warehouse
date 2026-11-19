.PHONY: install lint typecheck test check load dbt-build cost-check clean

install:
	pip install -e ".[dev]"

lint:
	ruff check .
	ruff format --check .

typecheck:
	mypy

test:
	pytest

check: lint typecheck test

# Real loads into BigQuery (needs gcloud application-default credentials and GCP_PROJECT).
load:
	hurricane-load tracks
	hurricane-load weather

dbt-build:
	dbt build --profiles-dir .

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage target dbt_packages logs

# Dry runs of every compiled model: fails if one would read more than 200 MB.
cost-check:
	dbt compile --profiles-dir .
	python -m hurricane_loaders.cost_check target/manifest.json --budget-mb 200
