"""The islands' daily weather from Open-Meteo's historical API (HTTP and BigQuery mocked)."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import httpx
import pytest
import respx
from google.cloud import bigquery

from hurricane_loaders.islands import ISLANDS
from hurricane_loaders.weather import (
    ARCHIVE_URL,
    MAX_ATTEMPTS,
    MAX_BYTES,
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


def test_window_reloads_the_last_ten_days_and_ends_a_week_ago() -> None:
    """The archive can fill or revise its latest days after a first load."""
    assert weather_window(None, date(2026, 11, 18)) == (date(1940, 1, 1), date(2026, 11, 11))
    assert weather_window(date(2026, 11, 1), date(2026, 11, 18)) == (
        date(2026, 10, 22),
        date(2026, 11, 11),
    )


@respx.mock
def test_rate_limited_requests_wait_and_retry() -> None:
    """A decade of data counts as dozens of calls for Open-Meteo, which answers 429 when
    the per-minute allowance is spent: the loader waits and asks again."""
    respx.get(ARCHIVE_URL).mock(side_effect=[httpx.Response(429), httpx.Response(200, json=DAILY)])
    waits: list[float] = []
    with httpx.Client() as client:
        rows = fetch_daily(client, GUADELOUPE, date(1989, 9, 16), date(1989, 9, 17), waits.append)
    assert len(rows) == 2
    assert waits == [61]


def test_the_delete_is_capped_too() -> None:
    """Every query the loaders run carries a byte cap, the DELETE included."""
    bq = MagicMock(spec=bigquery.Client)
    load_weather(bq, [], "p", date(2020, 1, 1), date(2020, 1, 2))
    (_,), kwargs = bq.query.call_args
    assert kwargs["job_config"].maximum_bytes_billed == MAX_BYTES


@respx.mock
def test_no_wait_after_the_last_attempt() -> None:
    respx.get(ARCHIVE_URL).mock(return_value=httpx.Response(429))
    waits: list[float] = []
    with httpx.Client() as client, pytest.raises(httpx.HTTPStatusError):
        fetch_daily(client, GUADELOUPE, date(1989, 9, 16), date(1989, 9, 17), waits.append)
    assert len(waits) == MAX_ATTEMPTS - 1


@respx.mock
def test_server_errors_and_timeouts_are_retried() -> None:
    respx.get(ARCHIVE_URL).mock(
        side_effect=[
            httpx.Response(502),
            httpx.ReadTimeout("slow"),
            httpx.Response(200, json=DAILY),
        ]
    )
    waits: list[float] = []
    with httpx.Client() as client:
        rows = fetch_daily(client, GUADELOUPE, date(1989, 9, 16), date(1989, 9, 17), waits.append)
    assert len(rows) == 2 and len(waits) == 2
