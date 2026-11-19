# Antilles hurricane warehouse — design

## Intent

The "cloud warehouse" project of the portfolio roadmap (`antilles-data-pipeline/docs/ROADMAP.md`,
phase 4): dbt models on a real cloud warehouse, cost-aware. The owner picked **BigQuery
with a billing account** (card attached, kept inside the free tier with budget alerts) and a
new subject distinct from the climate lakehouse: **the hurricanes that passed near the
Antilles since 1851**, from NOAA's IBTrACS best tracks, joined with the daily weather of
each island since 1940 (Open-Meteo's historical reanalysis). The owner chose this weather
source over the batch pipeline's S3 lake, which only holds a few months of forecasts for two
islands and would have required a long-lived AWS key. The project shows what warehouse
missions ask for: dbt on BigQuery, incremental models, partitioning and clustering, cost
control, data tests, documentation, scheduled runs, keyless CI authentication.

## Goals

- New public repository `antilles-hurricane-warehouse`, dbt project with the BigQuery
  adapter, Python only for loading and tooling (3.12, ruff, mypy `--strict`, pytest).
- Sources:
  - IBTrACS tracks: the BigQuery public table `bigquery-public-data.noaa_hurricanes.hurricanes`
    if it is current; otherwise NOAA's official IBTrACS CSV (North Atlantic file) loaded
    into our dataset by a Python job. Only the North Atlantic basin is kept.
  - Daily weather of the six islands (rain sum, maximum wind, maximum gusts, minimum
    pressure where available) from Open-Meteo's historical weather API (ERA5 reanalysis,
    1940 onward), at each island's point, loaded into BigQuery by a Python job: the full
    history once, then the latest days each run.
- dbt layers: staging (typed, renamed), intermediate (track points near each island,
  distance computed with BigQuery GIS), marts:
  - `fct_storm_passages`: one row per storm and island, closest approach (km), maximum wind
    within 100 km, Saffir-Simpson category, dates;
  - `agg_passages_by_decade`: passages per island and decade by category;
  - `fct_current_season`: the current season's storms near the Antilles;
  - `fct_passage_weather`: the island's rain and wind (reanalysis) on the days around each
    passage since 1940, next to the storm's wind at closest approach.
- Cost control as a feature: the public table copied once into a partitioned (by season)
  and clustered table; `maximum_bytes_billed` on every dbt run; a CI step that dry-runs the
  compiled models and fails above a byte budget per model; a GCP budget with alerts.
- Daily scheduled run (GitHub Actions) authenticating with Workload Identity Federation (no
  service account key).
- dbt docs published (GitHub Pages), README with a chart and the cost figures, French page
  on `/projets`, portfolio root README/CLAUDE.md.

## Non-goals

- dbt Cloud, Snowflake, Looker or any BI tool.
- Basins other than the North Atlantic; forecasting.
- Any dependency on the batch pipeline or on AWS.

## Anti-goals

- A bill: anything that could exceed the free tier unnoticed (full scans of public tables
  in every run, unpartitioned tables, no byte cap).
- Credentials in the repository or long-lived keys in GitHub secrets.
- Tests that read real tables or call NOAA or Open-Meteo. (CI may call BigQuery for
  zero-byte work: dry-runs of the compiled models and dbt unit tests on literal fixtures,
  which reference no table — my call, see "CI".)

## Constraints

- GCP: the owner creates the project and the billing account (card), attaches a budget
  (e.g. 5 €, alerts at 50/90/100 %), and authenticates `gcloud` locally. Region
  `europe-west1` or `US` multi-region to match the public dataset location (public datasets
  live in `US`; a cross-location query is impossible): the builder picks `US` if the public
  table is used.
- Free tier: 10 GB storage and 1 TB queried per month. The project must stay orders of
  magnitude below.
- Open-Meteo historical API: free for non-commercial use, rate-limited; the loader requests
  one island at a time and the full history only once.
- Repository rules as in the other projects: English code and docs, `make check` before
  every commit, one PR per feature, no real external calls in pytest (HTTP and the BigQuery
  client mocked; fixtures).
- The shell allowlist (lean-ctx) may block `gcloud`, `bq`, `dbt`: the owner allows them.

## Approaches

| Approach | Trade-off |
| --- | --- |
| **New repo, hurricanes + island weather history on BigQuery, GitHub Actions + WIF** (chosen) | New subject, every warehouse practice; more setup (GCP project, WIF). The owner later replaced the batch lake by Open-Meteo history as the weather source. |
| BigQuery target added to the batch dbt project | Portability shown with little code; tiny volume, little to say about cost, not a new project. |
| Same as the first with dbt Cloud | Hosted UI and docs; dependence on a third-party account to keep active. |

## Design

### Repository

```
antilles-hurricane-warehouse/
├── loaders/            Python: IBTrACS (public copy or NOAA CSV), Open-Meteo history → BigQuery
├── models/             dbt: staging/, intermediate/, marts/ (+ .yml with tests and docs)
├── macros/             distance and category helpers
├── tests/              pytest for loaders; dbt unit tests in models/*.yml
├── scripts/cost_check.py  dry-run every compiled model, fail above the byte budget
├── infra/              Terraform for GCP: dataset(s), WIF pool/provider, service account,
│                       budget (the owner approves plan/apply)
└── .github/workflows/  ci.yml (lint, types, tests, dbt compile + cost check), daily.yml
```

### Islands and distance

Island points (centroids) for Guadeloupe, Martinique, Saint-Barthélemy, Saint-Martin,
Dominica, Saint Lucia in a seed; a passage is any track point within 100 km
(`ST_DISTANCE` on `ST_GEOGPOINT`), keeping per storm and island the closest point and the
maximum wind within the radius. Saffir-Simpson category from the maximum sustained wind (kt).

### CI (my calls)

- Workload Identity Federation bound to this repository only (attribute condition on
  `assertion.repository`), so runs on `main` and on pull requests from branches of this
  repository can reach BigQuery; pull requests from forks get no token and skip the
  BigQuery steps.
- On every pull request: lint, types, pytest (no network), `dbt build --select
  test_type:unit` and the dry-run cost check. Both read no table: zero bytes billed.
- On `main`, daily: the loaders, then `dbt build`, with `maximum_bytes_billed`.

### Incremental

The track table is incremental by season (insert_overwrite on the season partition): the
daily run rewrites only the current season. The islands' weather is incremental by date.

## Left to the builder

- Exact IBTrACS columns (from `bq show` on the public table, or the NOAA CSV header) and
  whether the public table is current enough (latest season present).
- Terraform vs `gcloud` for the WIF setup (Terraform preferred, as in the batch repo).
- The byte budget per model.
- Chart tooling for the README.
