"""The islands' daily weather from Open-Meteo's historical API (HTTP and BigQuery mocked)."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import httpx
import respx
from google.cloud import bigquery

from hurricane_loaders.islands import ISLANDS
from hurricane_loaders.weather import (
    ARCHIVE_URL,
    decades,
    fetch_daily,
    load_weather,
    weather_window,
)

DAILY = json.loads((Path(__file__).parent / "fixtures" / "open_meteo_daily.json").read_text())
GUADELOUPE = ISLANDS[0]


@respx.mock
def test_fetch_daily_asks_for_the_island_point_in_utc() -> None:
    route = respx.get(ARCHIVE_URL).mock(return_value=httpx.Response(200, json=DAILY))
    with httpx.Client() as client:
        rows = fetch_daily(client, GUADELOUPE, date(1989, 9, 16), date(1989, 9, 17))

    params = dict(route.calls.last.request.url.params)
    assert params["latitude"] == "16.25" and params["longitude"] == "-61.55"
    assert params["timezone"] == "UTC"
    assert params["start_date"] == "1989-09-16" and params["end_date"] == "1989-09-17"
    assert rows[1] == {
        "island": "Guadeloupe",
        "date": "1989-09-17",
        "precipitation_mm": 188.6,
        "wind_max_kmh": 96.1,
        "gust_max_kmh": None,
    }


def test_full_history_is_requested_by_decade() -> None:
    chunks = decades(date(1940, 1, 1), date(2026, 11, 11))
    assert chunks[0] == (date(1940, 1, 1), date(1949, 12, 31))
    assert chunks[-1] == (date(2020, 1, 1), date(2026, 11, 11))
    assert len(chunks) == 9


def test_reloading_days_replaces_them() -> None:
    bq = MagicMock(spec=bigquery.Client)
    rows = [{"island": "Guadeloupe", "date": "1989-09-17", "precipitation_mm": 1.0,
             "wind_max_kmh": 2.0, "gust_max_kmh": 3.0}]  # fmt: skip
    assert load_weather(bq, rows, "p", date(1989, 9, 16), date(1989, 9, 17)) == 1

    (sql,), kwargs = bq.query.call_args
    assert sql.startswith("DELETE FROM `p.raw.island_weather`")
    params = {p.name: p.value for p in kwargs["job_config"].query_parameters}
    assert params == {"start": date(1989, 9, 16), "end": date(1989, 9, 17)}
    _, load_kwargs = bq.load_table_from_json.call_args
    assert load_kwargs["job_config"].write_disposition == bigquery.WriteDisposition.WRITE_APPEND


def test_window_starts_after_the_latest_day_and_ends_a_week_ago() -> None:
    assert weather_window(None, date(2026, 11, 18)) == (date(1940, 1, 1), date(2026, 11, 11))
    assert weather_window(date(2026, 11, 1), date(2026, 11, 18)) == (
        date(2026, 11, 2),
        date(2026, 11, 11),
    )
