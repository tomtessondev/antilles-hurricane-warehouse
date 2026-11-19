# Antilles Hurricane Warehouse Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A new repository that loads North Atlantic hurricane tracks and the six islands' daily weather history into BigQuery and models, with dbt, every storm passage near the Antilles since 1851, cost-controlled and run daily from GitHub Actions without keys.

**Architecture:** Two Python loaders write raw tables in a BigQuery dataset (`raw`); a dbt project builds staging, intermediate and mart tables on top. Terraform creates the GCP side (service account, Workload Identity Federation, budget). CI runs pytest offline and zero-byte BigQuery work (dbt unit tests, dry-run cost check); a daily workflow loads and builds.

**Tech Stack:** Python 3.12, google-cloud-bigquery, httpx + respx, dbt-core + dbt-bigquery (BigQuery GIS), Terraform (google provider), GitHub Actions + google-github-actions/auth, matplotlib.

**Spec:** `docs/superpowers/specs/2026-11-17-hurricane-warehouse-design.md`

## Global Constraints

- Repository `antilles-hurricane-warehouse` in the portfolio folder; package `hurricane_loaders` (src layout); English code/docs/commits; `make check` (ruff, ruff format --check, mypy --strict on `src`, pytest) before every commit; pytest never calls the network.
- BigQuery location `US` (same as public datasets); datasets `raw` (loaders), `staging`, `intermediate`, `marts` (dbt, custom schema names used as-is via a `generate_schema_name` macro).
- Islands (seed `islands.csv` and `hurricane_loaders.islands.ISLANDS`, identical): Guadeloupe 16.25,-61.55; Martinique 14.64,-61.02; Saint-Barthelemy 17.90,-62.83; Saint-Martin 18.07,-63.06; Dominica 15.42,-61.35; Saint Lucia 13.91,-60.98.
- Passage = a track point within 100 km of an island point (`ST_DWITHIN(ST_GEOGPOINT(lon, lat), island, 100000)`); Saffir-Simpson from maximum sustained wind in knots: TS < 64, Cat 1 64–82, 2 83–95, 3 96–112, 4 113–136, 5 ≥ 137; below 34 kt = depression.
- North Atlantic basin only (`basin = 'NA'`).
- Cost: dbt `maximum_bytes_billed: 1000000000` (1 GB) per query; CI cost check fails a model whose dry run exceeds 200 MB; GCP budget 5 € with alerts at 50/90/100 %.
- Weather: Open-Meteo historical API `https://archive-api.open-meteo.com/v1/archive`, daily `precipitation_sum, wind_speed_10m_max, wind_gusts_10m_max`, `timezone=UTC` (track times are UTC too), 1940-01-01 to the last available day.
- Owner actions and approvals: GCP project + billing + budget creation, `gcloud auth`, lean-ctx allowlist (`gcloud`, `bq`, `dbt`, `terraform`), every `terraform apply`, GitHub repository creation, merges.

## Review Focus

- A storm that passes within 100 km of two islands must give one row per island, each with its own closest approach — Task 5 unit test `passage_per_storm_and_island`.
- A track point at 101 km must not count as a passage — Task 5 unit test `just_outside_the_radius`.
- Early storms with no wind value must keep a row with a null category, not fail or vanish — Task 5 unit test `unknown_wind_gives_null_category`.
- Loading the same weather days twice must not duplicate rows — Task 4 `test_reloading_days_replaces_them`.
- Every dbt query must carry the byte cap — Task 5 `test_profiles_cap_bytes_billed` (pytest parses `profiles.yml`).

---

### Task 1: Repository skeleton and the islands

**Files:** `pyproject.toml`, `Makefile`, `.gitignore`, `README.md` (stub), `CLAUDE.md`, `.github/workflows/ci.yml` (lint, types, pytest), `src/hurricane_loaders/__init__.py`, `src/hurricane_loaders/islands.py`, `seeds/islands.csv`, `tests/test_islands.py`

**Interfaces — produces:** `@dataclass(frozen=True) class Island: name: str; lat: float; lon: float`; `ISLANDS: tuple[Island, ...]` (the six of Global Constraints).

- [ ] **Step 1:** `git init -b main`, empty initial commit, branch `feat/warehouse` (same flow as the lakehouse repo). Failing test `test_seed_and_module_agree`: `seeds/islands.csv` rows (name, lat, lon) equal `ISLANDS`.
- [ ] **Step 2–4:** RED; implement; `make check` green.
- [ ] **Step 5:** commit "Start the hurricane warehouse: package, islands, CI".

### Task 2: GCP project and infrastructure as code

**Files:** `infra/main.tf`, `infra/variables.tf`, `infra/outputs.tf`, `infra/README.md`, `infra/terraform.tfvars.example`

**Interfaces — produces (outputs):** `service_account_email`, `workload_identity_provider` (full resource name), dataset ids.

- [ ] **Step 1: owner actions** — create a GCP project and attach a billing account (card); enable BigQuery, IAM Credentials, STS, Billing Budgets APIs (`gcloud services enable …`); `! gcloud auth login` and `! gcloud auth application-default login`; allow `gcloud`, `bq`, `terraform` in lean-ctx.
- [ ] **Step 2:** Terraform (google provider pinned): datasets `raw`, `staging`, `intermediate`, `marts` (location US); service account `dbt-runner` with `roles/bigquery.jobUser` on the project and `roles/bigquery.dataEditor` on the four datasets; WIF pool `github` + OIDC provider `https://token.actions.githubusercontent.com`, `attribute_condition = "assertion.repository == 'tomtessondev/antilles-hurricane-warehouse'"`; `roles/iam.workloadIdentityUser` for `principalSet://…/attribute.repository/tomtessondev/antilles-hurricane-warehouse`; `google_billing_budget` 5 € (50/90/100 %). State in a GCS bucket created once by `gcloud storage buckets create` (versioned), backend config in `infra/README.md`.
- [ ] **Step 3:** `terraform fmt -check`, `terraform validate`, `terraform plan` → **owner approves** → `terraform apply`. Ledger the outputs (not secrets).
- [ ] **Step 4:** commit "Describe the GCP side in Terraform: datasets, keyless CI, budget".

### Task 3: Hurricane tracks loader

**Files:** `src/hurricane_loaders/tracks.py`, `tests/test_tracks.py`, `tests/fixtures/ibtracs_na_sample.csv` (if the CSV path is used)

**Interfaces — produces:** `def public_table_is_current(client: bigquery.Client, today: date) -> bool` (latest `season` ≥ `today.year - 1`); `def load_tracks(client: bigquery.Client, today: date) -> int` writing `raw.tracks` (partitioned by integer range on `season` 1850–2100 step 1, clustered by `sid`), returns rows; columns: `sid, name, season, iso_time, lat, lon, wind_kt, pressure_hpa, nature, basin`.

- [ ] **Step 1:** inspect the public table (`bq show --schema bigquery-public-data:noaa_hurricanes.hurricanes`, latest season) and ledger the columns and freshness; if stale, use NOAA's `ibtracs.NA.list.v04r01.csv` (second header row = units, blanks = missing) and ledger it.
- [ ] **Step 2: failing tests** (BigQuery client mocked): `test_current_public_table_is_copied_with_one_query` (one `CREATE OR REPLACE TABLE … PARTITION BY RANGE_BUCKET(season, GENERATE_ARRAY(1850, 2100, 1)) CLUSTER BY sid AS SELECT … WHERE basin = 'NA'` job); `test_stale_public_table_falls_back_to_noaa_csv` (respx serves the fixture CSV; `load_table_from_file`/`load_table_from_dataframe` called with WRITE_TRUNCATE; units row skipped; blanks → None).
- [ ] **Step 3–4:** implement; `make check`.
- [ ] **Step 5:** commit "Load the North Atlantic hurricane tracks".

### Task 4: Island weather loader

**Files:** `src/hurricane_loaders/weather.py`, `src/hurricane_loaders/cli.py` (`hurricane-load tracks|weather [--since YYYY-MM-DD]`), `tests/test_weather.py`, `tests/fixtures/open_meteo_daily.json`

**Interfaces — produces:** `def fetch_daily(client: httpx.Client, island: Island, start: date, end: date) -> list[dict[str, Any]]`; `def load_weather(bq: bigquery.Client, rows: list[dict[str, Any]], start: date, end: date) -> int` into `raw.island_weather` (`island, date, precipitation_mm, wind_max_kmh, gust_max_kmh`, partitioned by `date` monthly, clustered by `island`).

- [ ] **Step 1: failing tests**: `test_fetch_daily_asks_for_the_island_point_in_utc` (respx asserts query params); `test_reloading_days_replaces_them` (the load job deletes the `[start, end]` range for those islands before inserting — one `DELETE … WHERE date BETWEEN` + load, both on the mock); `test_full_history_is_requested_by_decade` (one request per island per decade from 1940, to stay under the API limits).
- [ ] **Step 2–4:** implement (`--since` default: the day after the latest loaded date, or 1940-01-01 when the table is empty); `make check`.
- [ ] **Step 5:** commit "Load the six islands' daily weather since 1940".

### Task 5: dbt models and tests

**Files:** `dbt_project.yml`, `profiles.yml` (env-driven: `GCP_PROJECT`, method `oauth` — ADC locally and via WIF in CI), `packages.yml` if needed, `macros/generate_schema_name.sql`, `macros/saffir_simpson.sql`, `models/staging/{stg_tracks,stg_island_weather}.sql`, `models/intermediate/int_track_points_near_islands.sql`, `models/marts/{fct_storm_passages,agg_passages_by_decade,fct_current_season,fct_passage_weather}.sql`, `models/**/*.yml` (sources, docs, data tests, unit tests), `tests/test_profiles.py`

**Interfaces — produces:** the four marts of the spec; `fct_storm_passages(sid, name, season, island, closest_km, closest_time, max_wind_kt_within_100km, category, first_time, last_time)`; `fct_passage_weather(sid, island, date, precipitation_mm, gust_max_kmh, max_wind_kt_within_100km)` for the passage day ± 1.

- [ ] **Step 1: failing tests**: dbt unit tests in `models/intermediate/*.yml` and `models/marts/*.yml` with literal inputs — `passage_per_storm_and_island`, `just_outside_the_radius`, `unknown_wind_gives_null_category`, `closest_point_is_kept`, `category_boundaries` (63/64/82/83/…/137 kt); pytest `test_profiles_cap_bytes_billed` (every output has `maximum_bytes_billed: 1000000000`). Data tests: `not_null`/`unique` on keys, `accepted_values` on category and island.
- [ ] **Step 2:** `dbt build --select test_type:unit` → FAIL (models missing).
- [ ] **Step 3:** implement. `stg_tracks` incremental `insert_overwrite` on the season partition (the daily run rewrites the current season); `stg_island_weather` incremental on date.
- [ ] **Step 4:** load real data (`hurricane-load tracks`, `hurricane-load weather`), `dbt build` against BigQuery; ledger bytes billed per model (from the run results) and sanity figures (passages per island, a known storm: Hugo 1989 near Guadeloupe, Maria 2017 near Dominica).
- [ ] **Step 5:** commit "Model storm passages near the Antilles with dbt on BigQuery".

### Task 6: Cost check, CI and the daily run

**Files:** `scripts/cost_check.py`, `tests/test_cost_check.py`, `.github/workflows/ci.yml` (adds the BigQuery job), `.github/workflows/daily.yml`, `.github/workflows/docs.yml`

**Interfaces — produces:** `def check(manifest_dir: Path, client: bigquery.Client, budget_bytes: int) -> list[tuple[str, int]]` (models over budget); CLI exits 1 if any.

- [ ] **Step 1: failing test** `test_models_over_budget_fail` (mocked dry-run jobs returning bytes per model; one over 200 MB → returned and exit 1).
- [ ] **Step 2–4:** implement; workflows: CI job `bigquery` (`if: github.event.pull_request.head.repo.full_name == github.repository || github.event_name == 'push'`), auth with `google-github-actions/auth` (WIF provider + service account from repository variables), `dbt deps`, `dbt build --select test_type:unit`, `dbt compile` + cost check; `daily.yml` (cron 06:00 UTC + manual): loaders then `dbt build`; `docs.yml`: `dbt docs generate` → GitHub Pages. `make check` green.
- [ ] **Step 5:** commit "Check the cost of every model and run the warehouse daily".

### Task 7: Images, docs, publication

- [ ] **Step 1:** `scripts/charts.py` (passages per decade and island, by category; reads the marts with the BigQuery client) → `docs/images/`.
- [ ] **Step 2:** README (story, architecture, sources, models, cost section with the real bytes billed and the budget, how to run, CI without keys), `docs/ROADMAP.md`, `CLAUDE.md` final; `make check`; commit.
- [ ] **Step 3: owner approval** → `gh repo create tomtessondev/antilles-hurricane-warehouse --public`, push `main` and the branch, PR, repository variables for WIF, CI green; merge with the owner's go; first `daily` run and Pages.

### Task 8: Portfolio docs and the French page

**Files:** in `antilles-data-pipeline`: `dashboard/src/app/projets/antilles-hurricane-warehouse/page.tsx` (+ `_images/`), card on `/projets` (five projects), glossary terms (entrepôt de données, BigQuery, partitionnement, clustering, dry run, fédération d'identité), `docs/ROADMAP.md` (cloud warehouse done); portfolio root `README.md`, `CLAUDE.md` (row, GCP facts: project, location US, budget, owner approves `terraform apply`).

- [ ] **Step 1:** branch `docs/hurricane-warehouse`, page in the style of the lakehouse page.
- [ ] **Step 2:** dashboard lint/typecheck/test/build; root `make check`, `make transform`.
- [ ] **Step 3:** commit, push, PR after the owner's go; merge with the owner's go.
