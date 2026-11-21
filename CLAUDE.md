# CLAUDE.md

Context for Claude Code working in this repository.

## Purpose

Portfolio project (phase 4, cloud warehouse): North Atlantic hurricane tracks (NOAA
IBTrACS) and the six islands' daily weather history (Open-Meteo reanalysis) loaded into
BigQuery, modelled with dbt into storm passages near the Antilles. The owner is an FPGA /
embedded engineer moving toward freelance data engineering, so code quality, tests and
clear docs matter more than feature count. Every change should be something a recruiter
can read.

## Stack

- Python 3.12+ package `src/hurricane_loaders` (loaders, CLI `hurricane-load`)
  - `islands.py`: the six island points (same as `seeds/islands.csv`, a test checks it)
  - `export.py`: `hurricane-load export --out FILE`, the marts as `hurricanes.json` for the
    portfolio site's explorer; `daily.yml` publishes it to the one-commit `data` branch
- dbt on BigQuery (project `antilles-hurricanes`, location `US`)
- pytest (HTTP and the BigQuery client mocked), ruff, mypy --strict

## Commands

```bash
python -m venv .venv && source .venv/bin/activate
make install / check
```

## Rules

- Run `make check` before every commit; it must pass.
- Never call BigQuery, NOAA or Open-Meteo from pytest: fixtures, respx, mocks.
- Every BigQuery query is capped (`maximum_bytes_billed`); keep the project far inside the
  free tier (budget 5 USD, the billing account's currency, with alerts).
- `hurricanes.json` is a contract with the site (`antilles-data-pipeline/dashboard`,
  `src/lib/hurricanes.ts`): change both together, and keep the file under 1 MB.
- `terraform apply` only after the owner approves the plan.
- Keep mypy strict; no `type: ignore` without a comment explaining why.
- Code, comments, commits and README in English.
- Small commits with clear messages; open a PR per feature so CI runs.
