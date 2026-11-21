"""The JSON export for the site's explorer (the BigQuery client is mocked)."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from google.cloud import bigquery

from hurricane_loaders import export
from hurricane_loaders.cli import main

T0 = datetime(2017, 9, 18, 6, tzinfo=UTC)

ROWS: dict[str, list[dict[str, Any]]] = {
    "staging.islands": [{"name": "Dominica", "lat": 15.42, "lon": -61.35}],
    "marts.fct_storm_passages": [
        {
            "passage_id": "S1-Dominica",
            "sid": "S1",
            "name": "MARIA",
            "season": 2017,
            "island": "Dominica",
            "closest_km": 4.987,
            "closest_time": T0,
            "max_wind_kt_within_100km": 145,
            "category": "Cat 5",
        }
    ],
    "marts.fct_passage_weather": [
        {
            "passage_id": "S1-Dominica",
            "date": date(2017, 9, 18),
            "day_offset": 0,
            "precipitation_mm": 120.04,
            "wind_max_kmh": 88.0,
            "gust_max_kmh": None,
        }
    ],
    "marts.agg_passages_by_decade": [
        {"island": "Dominica", "decade": 2010, "category": "Cat 5", "passages": 1}
    ],
    "staging.stg_tracks": [
        {
            "sid": "S1",
            "name": "MARIA",
            "season": 2017,
            "lon": -61.349,
            "lat": 15.4499,
            "wind_kt": 145,
        },
        {
            "sid": "S1",
            "name": "MARIA",
            "season": 2017,
            "lon": -10.0,
            "lat": 50.0,
            "wind_kt": 40,
        },
        {
            "sid": "S2",
            "name": "UNNAMED",
            "season": 1851,
            "lon": -60.04,
            "lat": 14.96,
            "wind_kt": None,
        },
    ],
}


def fake_client() -> MagicMock:
    def query(sql: str, job_config: bigquery.QueryJobConfig) -> MagicMock:
        # The tracks query names the passages too: match on its FROM clause.
        table = next(t for t in ROWS if f".{t}`" in sql.split("WHERE")[0])
        job = MagicMock()
        job.result.return_value = ROWS[table]
        return job

    bq = MagicMock(spec=bigquery.Client)
    bq.query.side_effect = query
    return bq


def test_document_follows_the_contract() -> None:
    doc = export.build(fake_client(), "p", T0)

    assert doc["generated_at"] == "2017-09-18T06:00:00Z"
    assert doc["islands"] == [{"island": "Dominica", "lat": 15.42, "lon": -61.35}]
    assert doc["passages"] == [
        {
            "passage_id": "S1-Dominica",
            "sid": "S1",
            "name": "MARIA",
            "season": 2017,
            "island": "Dominica",
            "closest_km": 5.0,
            "closest_time": "2017-09-18T06:00:00Z",
            "max_wind_kt": 145,
            "category": "Cat 5",
        }
    ]
    assert doc["passage_weather"] == [
        {
            "passage_id": "S1-Dominica",
            "date": "2017-09-18",
            "day_offset": 0,
            "precipitation_mm": 120.0,
            "wind_max_kmh": 88.0,
            "gust_max_kmh": None,
        }
    ]
    assert doc["by_decade"] == ROWS["marts.agg_passages_by_decade"]
    assert list(doc["tracks"][0]) == ["sid", "name", "season", "points"]


def test_tracks_are_clipped_rounded_and_keep_unknown_wind() -> None:
    doc = export.build(fake_client(), "p", T0)

    assert doc["tracks"] == [
        {
            "sid": "S1",
            "name": "MARIA",
            "season": 2017,
            "points": [(-61.3, 15.4, 145)],
        },
        {
            "sid": "S2",
            "name": "UNNAMED",
            "season": 1851,
            "points": [(-60.0, 15.0, None)],
        },
    ]


def test_tracks_are_only_the_storms_that_passed() -> None:
    bq = fake_client()
    export.tracks(bq, "p")
    sql = bq.query.call_args.args[0]
    assert "`p.staging.stg_tracks`" in sql
    assert "sid IN (SELECT DISTINCT sid FROM `p.marts.fct_storm_passages`)" in sql


def test_window_edges_are_kept() -> None:
    edges = [
        {"lon": -100.0, "lat": 0.0, "wind_kt": 30},
        {"lon": -20.0, "lat": 45.0, "wind_kt": 30},
        {"lon": -100.05, "lat": 10.0, "wind_kt": 30},
        {"lon": -50.0, "lat": -0.1, "wind_kt": 30},
    ]
    assert [p[:2] for p in export.clip_points(edges)] == [(-100.0, 0.0), (-20.0, 45.0)]


def test_every_query_is_capped() -> None:
    bq = fake_client()
    export.build(bq, "p", T0)

    assert bq.query.call_count == 5
    for call in bq.query.call_args_list:
        assert call.kwargs["job_config"].maximum_bytes_billed == 100_000_000


def test_times_are_utc_with_z() -> None:
    paris = datetime.fromisoformat("2017-09-18T08:00:00+02:00")
    assert export.iso_time(paris) == "2017-09-18T06:00:00Z"


def test_written_json_is_compact_and_null_stays_null(tmp_path: Path) -> None:
    out = tmp_path / "out" / "hurricanes.json"
    size = export.write(export.build(fake_client(), "p", T0), out)

    text = out.read_text()
    assert size == len(text.encode())
    assert ": " not in text and ", " not in text
    assert json.loads(text)["tracks"][1]["points"] == [[-60.0, 15.0, None]]


@pytest.mark.parametrize("argv", [["export"], ["tracks", "--out", "x.json"]])
def test_out_goes_with_export_only(argv: list[str], capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(argv)
    assert exit_info.value.code == 2
    assert "--out" in capsys.readouterr().err
