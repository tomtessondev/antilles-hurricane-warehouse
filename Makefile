.PHONY: install lint typecheck test check load dbt-build clean

install:
	pip install -e ".[dev]"
	dbt deps

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
	dbt build

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage target dbt_packages logs
