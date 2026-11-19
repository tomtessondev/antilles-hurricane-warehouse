"""Dry-runs every compiled dbt model and fails when one would scan more than the budget.

A BigQuery dry run plans the query and reports the bytes it would read, without running
or billing it: CI catches a model that lost its partition filter before it reaches the
daily run. Usage: `python -m hurricane_loaders.cost_check target/manifest.json`.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from google.cloud import bigquery


def check(manifest: Path, bq: bigquery.Client, budget_bytes: int) -> list[tuple[str, int]]:
    """The models whose dry run reads more than `budget_bytes`, with what they would read."""
    nodes = json.loads(manifest.read_text())["nodes"].values()
    over = []
    for node in nodes:
        if node["resource_type"] != "model":
            continue
        job = bq.query(
            node["compiled_code"],
            job_config=bigquery.QueryJobConfig(dry_run=True, use_query_cache=False),
        )
        scanned = job.total_bytes_processed or 0
        print(f"{node['name']}: {scanned / 1e6:.1f} MB")
        if scanned > budget_bytes:
            over.append((node["name"], scanned))
    return over


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="cost-check")
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--budget-mb", type=int, default=200)
    args = parser.parse_args(argv)

    bq = bigquery.Client(project=os.getenv("GCP_PROJECT", "antilles-hurricanes"))
    over = check(args.manifest, bq, args.budget_mb * 1_000_000)
    for name, scanned in over:
        print(f"{name} would read {scanned / 1e6:.0f} MB, over {args.budget_mb} MB")
    sys.exit(1 if over else 0)


if __name__ == "__main__":
    main()
