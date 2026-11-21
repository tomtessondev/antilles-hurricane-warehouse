"""The marts as one small JSON document (`hurricanes.json`) for the portfolio site's
explorer: the islands, the storm passages, the islands' weather around each passage, the
passages per decade and the tracks of the storms that passed. The daily workflow publishes
it to the repository's `data` branch; the site validates it against the same contract.

Every query is capped like the loaders'; the whole export reads a few MB.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from google.cloud import bigquery

MAX_BYTES = 100_000_000
# The map's window: the North Atlantic, from the Gulf of Mexico to the Azores.
LON_RANGE = (-100.0, -20.0)
LAT_RANGE = (0.0, 45.0)

Point = tuple[float, float, int | None, str]


def iso_time(value: datetime) -> str:
    """UTC, to the second, with a "Z": `1979-08-29T12:00:00Z`."""
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _rows(bq: bigquery.Client, sql: str) -> list[dict[str, Any]]:
    job = bq.query(sql, job_config=bigquery.QueryJobConfig(maximum_bytes_billed=MAX_BYTES))
    return [dict(row.items()) for row in job.result()]


def _round(value: float | None, digits: int = 1) -> float | None:
    return None if value is None else round(value, digits)


def islands(bq: bigquery.Client, project: str) -> list[dict[str, Any]]:
    rows = _rows(bq, f"SELECT name, lat, lon FROM `{project}.staging.islands` ORDER BY name")
    return [{"island": r["name"], "lat": r["lat"], "lon": r["lon"]} for r in rows]


def passages(bq: bigquery.Client, project: str) -> list[dict[str, Any]]:
    rows = _rows(
        bq,
        f"""
        SELECT passage_id, sid, name, season, island, closest_km, closest_time,
            max_wind_kt_within_100km, category
        FROM `{project}.marts.fct_storm_passages`
        ORDER BY closest_time, island
        """,
    )
    return [
        {
            "passage_id": r["passage_id"],
            "sid": r["sid"],
            "name": r["name"],
            "season": r["season"],
            "island": r["island"],
            "closest_km": _round(r["closest_km"]),
            "closest_time": iso_time(r["closest_time"]),
            "max_wind_kt": r["max_wind_kt_within_100km"],
            "category": r["category"],
        }
        for r in rows
    ]


def passage_weather(bq: bigquery.Client, project: str) -> list[dict[str, Any]]:
    rows = _rows(
        bq,
        f"""
        SELECT passage_id, date, day_offset, precipitation_mm, wind_max_kmh, gust_max_kmh
        FROM `{project}.marts.fct_passage_weather`
        ORDER BY passage_id, date
        """,
    )
    return [
        {
            "passage_id": r["passage_id"],
            "date": date.isoformat(r["date"]),
            "day_offset": r["day_offset"],
            "precipitation_mm": _round(r["precipitation_mm"]),
            "wind_max_kmh": _round(r["wind_max_kmh"]),
            "gust_max_kmh": _round(r["gust_max_kmh"]),
        }
        for r in rows
    ]


def by_decade(bq: bigquery.Client, project: str) -> list[dict[str, Any]]:
    return _rows(
        bq,
        f"""
        SELECT island, decade, category, passages
        FROM `{project}.marts.agg_passages_by_decade`
        ORDER BY island, decade, category
        """,
    )


def clip_points(fixes: Iterable[dict[str, Any]]) -> list[Point]:
    """The fixes inside the map's window, as compact `[lon, lat, wind_kt, time]` points
    rounded to 0.1° (about 11 km, finer than the map draws). Unknown wind stays null."""
    points: list[Point] = []
    for fix in fixes:
        if not (
            LON_RANGE[0] <= fix["lon"] <= LON_RANGE[1]
            and LAT_RANGE[0] <= fix["lat"] <= LAT_RANGE[1]
        ):
            continue
        points.append(
            (round(fix["lon"], 1), round(fix["lat"], 1), fix["wind_kt"], iso_time(fix["iso_time"]))
        )
    return points


def tracks(bq: bigquery.Client, project: str) -> list[dict[str, Any]]:
    """The tracks of the storms that passed near an island, one entry per storm."""
    rows = _rows(
        bq,
        f"""
        SELECT sid, name, season, iso_time, lon, lat, wind_kt
        FROM `{project}.staging.stg_tracks`
        WHERE sid IN (SELECT DISTINCT sid FROM `{project}.marts.fct_storm_passages`)
        ORDER BY season, sid, iso_time
        """,
    )
    storms: dict[str, dict[str, Any]] = {}
    fixes: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        storms.setdefault(r["sid"], {"sid": r["sid"], "name": r["name"], "season": r["season"]})
        fixes.setdefault(r["sid"], []).append(r)
    return [{**storm, "points": clip_points(fixes[sid])} for sid, storm in storms.items()]


def build(bq: bigquery.Client, project: str, now: datetime) -> dict[str, Any]:
    return {
        "generated_at": iso_time(now),
        "islands": islands(bq, project),
        "passages": passages(bq, project),
        "passage_weather": passage_weather(bq, project),
        "by_decade": by_decade(bq, project),
        "tracks": tracks(bq, project),
    }


def write(document: dict[str, Any], out: Path) -> int:
    """Compact JSON (no spaces): the site downloads it whole. Returns the size in bytes."""
    text = json.dumps(document, separators=(",", ":"), ensure_ascii=False)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    return len(text.encode("utf-8"))
