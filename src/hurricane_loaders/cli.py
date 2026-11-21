"""`hurricane-load tracks | weather [--since YYYY-MM-DD]`: the loaders the daily workflow
runs before dbt; `hurricane-load export --out FILE`: the marts as one JSON document, run
after it. The project comes from GCP_PROJECT (default antilles-hurricanes)."""

from __future__ import annotations

import argparse
import os
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
from google.api_core.exceptions import NotFound
from google.cloud import bigquery

from hurricane_loaders import export
from hurricane_loaders.islands import ISLANDS
from hurricane_loaders.tracks import download_lines, load_tracks, parse_tracks
from hurricane_loaders.weather import (
    MAX_BYTES,
    decades,
    fetch_daily,
    load_weather,
    weather_window,
)


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
    parser.add_argument("source", choices=("tracks", "weather", "export"))
    parser.add_argument(
        "--since", type=date.fromisoformat, help="weather only: first day to (re)load"
    )
    parser.add_argument("--out", type=Path, help="export only: the JSON file to write")
    args = parser.parse_args(argv)
    # Checked before connecting to anything: a wrong command fails fast and says why.
    if args.since and args.source != "weather":
        parser.error("--since only applies to weather (the tracks file is loaded whole)")
    if (args.source == "export") != (args.out is not None):
        parser.error("--out is required by export and only applies to it")
    last_day = weather_window(None, date.today())[1]
    if args.since and args.since > last_day:
        parser.error(f"--since {args.since} is after the last day available ({last_day})")

    project = os.getenv("GCP_PROJECT", "antilles-hurricanes")
    bq = bigquery.Client(project=project)
    if args.source == "export":
        document = export.build(bq, project, datetime.now(UTC))
        try:
            size = export.write(document, args.out)
        except export.ExportError as error:
            raise SystemExit(f"hurricane-load export: {error}") from error
        points = sum(len(track["points"]) for track in document["tracks"])
        print(
            f"Wrote {args.out} ({size:,} bytes): {len(document['tracks'])} storms, "
            f"{points} track points, {len(document['passages'])} passages"
        )
        return
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
