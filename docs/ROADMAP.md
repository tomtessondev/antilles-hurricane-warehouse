# Roadmap

1. **Hurricane warehouse** (done). NOAA IBTrACS tracks and the islands' daily reanalysis
   weather in BigQuery; dbt staging, intermediate and marts with unit and data tests;
   partitioning, clustering, byte caps, dry-run cost check in CI and a budget; daily run
   from GitHub Actions with Workload Identity Federation; dbt docs on GitHub Pages.
2. **Storm surge and rain records.** Rank each island's wettest days since 1940 and show
   which ones a storm explains, as a mart and a chart.
3. **Wind radii.** IBTrACS gives the radius of 34-, 50- and 64-knot winds by quadrant:
   decide "the island was in hurricane-force winds" from the radii, not a fixed 100 km.
4. **Snapshots.** dbt snapshots of the current season's tracks, to show how NOAA revises a
   storm after the fact.
5. **Semantic layer.** dbt metrics (passages, rain on passage days) queried from a small
   page, once a BI tool earns its place.
