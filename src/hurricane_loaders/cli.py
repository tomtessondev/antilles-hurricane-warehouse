"""`hurricane-load tracks | weather [--since YYYY-MM-DD]`: the loaders the daily workflow
runs before dbt. The project comes from GCP_PROJECT (default antilles-hurricanes)."""

from __future__ import annotations

import argparse
import os
from datetime import date

import httpx
from google.api_core.exceptions import NotFound
from google.cloud import bigquery

from hurricane_loaders.islands import ISLANDS
from hurricane_loaders.tracks import download_lines, load_tracks, parse_tracks
from hurricane_loaders.weather import decades, fetch_daily, load_weather, weather_window

# A cap on every query the loaders run: the only one reads a single date column.
MAX_BYTES = 100_000_000


def _latest_weather_day(bq: bigquery.Client, project: str) -> date | None:
    try:
        bq.get_table(f"{project}.raw.island_weather")
    except NotFound:  # first run: the whole history
        return None
    rows = bq.query(
        f"SELECT MAX(date) AS latest FROM `{project}.raw.island_weather`",
        job_config=bigquery.QueryJobConfig(maximum_bytes_billed=MAX_BYTES),
    ).result()
    latest: date | None = next(iter(rows)).latest
    return latest


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="hurricane-load")
    parser.add_argument("source", choices=("tracks", "weather"))
    parser.add_argument("--since", type=date.fromisoformat, help="first day to (re)load")
    args = parser.parse_args(argv)

    project = os.getenv("GCP_PROJECT", "antilles-hurricanes")
    bq = bigquery.Client(project=project)
    with httpx.Client() as http:
        if args.source == "tracks":
            rows = list(parse_tracks(download_lines(http)))
            print(f"Loaded {load_tracks(bq, rows, project)} track fixes")
            return
        latest = None if args.since else _latest_weather_day(bq, project)
        start, end = weather_window(latest, date.today())
        if args.since:
            start = args.since
        if start > end:
            print("Weather is up to date")
            return
        rows = [
            row
            for island in ISLANDS
            for chunk_start, chunk_end in decades(start, end)
            for row in fetch_daily(http, island, chunk_start, chunk_end)
        ]
        print(f"Loaded {load_weather(bq, rows, project, start, end)} island-days")
