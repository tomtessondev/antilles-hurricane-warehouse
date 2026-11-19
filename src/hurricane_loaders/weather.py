"""Daily weather of each island since 1940, from Open-Meteo's historical weather API (ERA5
reanalysis at the island's point): rain, maximum wind and gusts, in UTC days like the
hurricane fixes. The full history is fetched once, a decade per request; later runs fetch
the days since the latest one loaded.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

import httpx
from google.cloud import bigquery

from hurricane_loaders.islands import Island

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
FIRST_DAY = date(1940, 1, 1)
DAILY = ("precipitation_sum", "wind_speed_10m_max", "wind_gusts_10m_max")
RATE_LIMIT_WAIT_S = 61
MAX_ATTEMPTS = 6

SCHEMA = [
    bigquery.SchemaField("island", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("date", "DATE", mode="REQUIRED"),
    bigquery.SchemaField("precipitation_mm", "FLOAT"),
    bigquery.SchemaField("wind_max_kmh", "FLOAT"),
    bigquery.SchemaField("gust_max_kmh", "FLOAT"),
]


def weather_window(latest: date | None, today: date) -> tuple[date, date]:
    """From the day after the latest one loaded (or 1940) to a week ago: the reanalysis
    reaches the archive with a few days' delay."""
    start = FIRST_DAY if latest is None else latest + timedelta(days=1)
    return start, today - timedelta(days=7)


def decades(start: date, end: date) -> list[tuple[date, date]]:
    """[start, end] cut at decade boundaries, to keep each request small."""
    chunks = []
    begin = start
    while begin <= end:
        stop = min(date(begin.year // 10 * 10 + 9, 12, 31), end)
        chunks.append((begin, stop))
        begin = date(stop.year + 1, 1, 1)
    return chunks


def fetch_daily(
    client: httpx.Client,
    island: Island,
    start: date,
    end: date,
    sleep: Callable[[float], None] = time.sleep,
) -> list[dict[str, Any]]:
    """Open-Meteo counts long requests as many calls and answers 429 once the per-minute
    allowance is spent: wait for the next minute and ask again."""
    params: dict[str, str | float] = {
        "latitude": island.lat,
        "longitude": island.lon,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "daily": ",".join(DAILY),
        "timezone": "UTC",
    }
    for _ in range(MAX_ATTEMPTS):
        response = client.get(ARCHIVE_URL, params=params, timeout=120)
        if response.status_code != 429:
            break
        sleep(RATE_LIMIT_WAIT_S)
    response.raise_for_status()
    daily = response.json()["daily"]
    return [
        {
            "island": island.name,
            "date": day,
            "precipitation_mm": rain,
            "wind_max_kmh": wind,
            "gust_max_kmh": gust,
        }
        for day, rain, wind, gust in zip(
            daily["time"], *(daily[name] for name in DAILY), strict=True
        )
    ]


def load_weather(
    bq: bigquery.Client, rows: list[dict[str, Any]], project: str, start: date, end: date
) -> int:
    """Replaces the days [start, end] in `raw.island_weather` (partitioned by month,
    clustered by island): loading the same days again does not duplicate them."""
    table = bigquery.Table(f"{project}.raw.island_weather", schema=SCHEMA)
    table.time_partitioning = bigquery.TimePartitioning(
        type_=bigquery.TimePartitioningType.MONTH, field="date"
    )
    table.clustering_fields = ["island"]
    bq.create_table(table, exists_ok=True)

    bq.query(
        f"DELETE FROM `{project}.raw.island_weather` WHERE date BETWEEN @start AND @end",
        job_config=bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("start", "DATE", start),
                bigquery.ScalarQueryParameter("end", "DATE", end),
            ]
        ),
    ).result()
    config = bigquery.LoadJobConfig(
        schema=SCHEMA, write_disposition=bigquery.WriteDisposition.WRITE_APPEND
    )
    bq.load_table_from_json(
        rows, destination=f"{project}.raw.island_weather", job_config=config
    ).result()
    return len(rows)
