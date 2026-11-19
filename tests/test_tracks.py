"""The NOAA IBTrACS North Atlantic file, parsed and loaded (HTTP and BigQuery mocked)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import httpx
import respx
from google.cloud import bigquery

from hurricane_loaders.tracks import IBTRACS_URL, download_lines, load_tracks, parse_tracks

HEADER, UNITS = (Path(__file__).parent / "fixtures" / "ibtracs_header.csv").read_text().splitlines()
COLUMNS = HEADER.split(",")


def line(**values: str) -> str:
    """One data line in the file's format: blank cells are a single space."""
    return ",".join(values.get(c, " ") for c in COLUMNS)


HUGO = dict(
    SID="1989254N13340", SEASON="1989", BASIN="NA", NAME="HUGO", ISO_TIME="1989-09-17 06:00:00",
    NATURE="TS", LAT="16.3", LON="-61.4", USA_WIND="120", USA_PRES="940", WMO_WIND="115",
    TRACK_TYPE="main",
)  # fmt: skip


def test_units_row_is_skipped_and_blanks_become_null() -> None:
    early = dict(HUGO, SID="1851175N26270", SEASON="1851", NAME="UNNAMED", USA_WIND=" ",
                 USA_PRES=" ", WMO_WIND=" ")  # fmt: skip
    rows = list(parse_tracks([HEADER, UNITS, line(**early)]))
    assert rows == [
        {
            "sid": "1851175N26270", "name": "UNNAMED", "season": 1851,
            "iso_time": "1989-09-17 06:00:00", "nature": "TS",
            "lat": 16.3, "lon": -61.4, "wind_kt": None, "pressure_hpa": None, "basin": "NA",
        }
    ]  # fmt: skip


def test_usa_values_first_then_wmo() -> None:
    (hugo,) = parse_tracks([HEADER, UNITS, line(**HUGO)])
    assert hugo["wind_kt"] == 120 and hugo["pressure_hpa"] == 940
    (wmo_only,) = parse_tracks([HEADER, UNITS, line(**dict(HUGO, USA_WIND=" "))])
    assert wmo_only["wind_kt"] == 115


def test_spur_tracks_are_left_out() -> None:
    rows = list(parse_tracks([HEADER, UNITS, line(**HUGO), line(**dict(HUGO, TRACK_TYPE="spur"))]))
    assert len(rows) == 1


@respx.mock
def test_download_streams_the_north_atlantic_file() -> None:
    respx.get(IBTRACS_URL).mock(
        return_value=httpx.Response(200, text="\n".join([HEADER, UNITS, line(**HUGO)]) + "\n")
    )
    with httpx.Client() as client:
        assert list(download_lines(client)) == [HEADER, UNITS, line(**HUGO)]


def test_load_replaces_a_table_partitioned_by_season() -> None:
    bq = MagicMock(spec=bigquery.Client)
    rows = list(parse_tracks([HEADER, UNITS, line(**HUGO)]))
    assert load_tracks(bq, rows, "antilles-hurricanes") == 1

    _, kwargs = bq.load_table_from_json.call_args
    config: bigquery.LoadJobConfig = kwargs["job_config"]
    assert kwargs["destination"] == "antilles-hurricanes.raw.tracks"
    assert config.write_disposition == bigquery.WriteDisposition.WRITE_TRUNCATE
    assert config.range_partitioning.field == "season"
    assert config.clustering_fields == ["sid"]


def test_provisional_tracks_of_the_current_season_are_kept() -> None:
    """NOAA marks the current season's storms PROVISIONAL until its post-season review."""
    rows = list(
        parse_tracks([HEADER, UNITS, line(**dict(HUGO, SEASON="2026", TRACK_TYPE="PROVISIONAL"))])
    )
    assert [r["season"] for r in rows] == [2026]
