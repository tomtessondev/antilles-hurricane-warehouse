"""North Atlantic hurricane tracks from NOAA's IBTrACS best-track archive.

The BigQuery public table `noaa_hurricanes.hurricanes` stops at the 2023 season, so the
official file is loaded instead: one row per storm and 3- or 6-hourly fix since 1851, a
second header row of units, blank cells written as a single space. The North Atlantic file
is replaced as a whole each run (about 60 MB): NOAA rewrites past seasons when it revises
them.
"""

from __future__ import annotations

import csv
from collections.abc import Iterable, Iterator
from typing import Any

import httpx
from google.cloud import bigquery

IBTRACS_URL = (
    "https://www.ncei.noaa.gov/data/international-best-track-archive-for-climate-stewardship-ibtracs"
    "/v04r01/access/csv/ibtracs.NA.list.v04r01.csv"
)

SCHEMA = [
    bigquery.SchemaField("sid", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("name", "STRING"),
    bigquery.SchemaField("season", "INTEGER", mode="REQUIRED"),
    bigquery.SchemaField("iso_time", "TIMESTAMP", mode="REQUIRED"),
    bigquery.SchemaField("nature", "STRING"),
    bigquery.SchemaField("lat", "FLOAT", mode="REQUIRED"),
    bigquery.SchemaField("lon", "FLOAT", mode="REQUIRED"),
    bigquery.SchemaField("wind_kt", "INTEGER"),
    bigquery.SchemaField("pressure_hpa", "INTEGER"),
    bigquery.SchemaField("basin", "STRING"),
]


def _value(row: dict[str, str], *columns: str) -> str | None:
    """The first non-blank of the given columns: the US agency's value is the reference in
    the North Atlantic, the WMO one fills the gaps."""
    for column in columns:
        cell = row[column].strip()
        if cell:
            return cell
    return None


def _int(text: str | None) -> int | None:
    return None if text is None else round(float(text))


def parse_tracks(lines: Iterable[str]) -> Iterator[dict[str, Any]]:
    """Main-track fixes of North Atlantic storms. Spur tracks (alternative positions of a
    storm's early or late life) are left out: they would duplicate fixes."""
    reader = csv.DictReader(lines)
    next(reader)  # the units row
    for row in reader:
        if row["TRACK_TYPE"].strip() != "main" or row["BASIN"].strip() != "NA":
            continue
        yield {
            "sid": row["SID"],
            "name": row["NAME"].strip() or None,
            "season": int(row["SEASON"]),
            "iso_time": row["ISO_TIME"],
            "nature": row["NATURE"].strip() or None,
            "lat": float(row["LAT"]),
            "lon": float(row["LON"]),
            "wind_kt": _int(_value(row, "USA_WIND", "WMO_WIND")),
            "pressure_hpa": _int(_value(row, "USA_PRES", "WMO_PRES")),
            "basin": row["BASIN"].strip(),
        }


def download_lines(client: httpx.Client) -> Iterator[str]:
    with client.stream("GET", IBTRACS_URL, timeout=300, follow_redirects=True) as response:
        response.raise_for_status()
        yield from response.iter_lines()


def load_tracks(bq: bigquery.Client, rows: list[dict[str, Any]], project: str) -> int:
    """Replaces `raw.tracks`, partitioned by season (integer range) and clustered by storm,
    so that models reading a few seasons or one storm scan only those."""
    config = bigquery.LoadJobConfig(
        schema=SCHEMA,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        range_partitioning=bigquery.RangePartitioning(
            field="season", range_=bigquery.PartitionRange(start=1850, end=2101, interval=1)
        ),
        clustering_fields=["sid"],
    )
    bq.load_table_from_json(rows, destination=f"{project}.raw.tracks", job_config=config).result()
    return len(rows)
