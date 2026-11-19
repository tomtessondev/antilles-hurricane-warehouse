"""The islands exist twice: in Python (weather loader) and as a dbt seed (passages). They
must be the same points."""

from __future__ import annotations

import csv
from pathlib import Path

from hurricane_loaders.islands import ISLANDS, Island

SEED = Path(__file__).resolve().parents[1] / "seeds" / "islands.csv"


def test_seed_and_module_agree() -> None:
    with SEED.open(encoding="utf-8") as f:
        rows = [Island(r["name"], float(r["lat"]), float(r["lon"])) for r in csv.DictReader(f)]
    assert tuple(rows) == ISLANDS
    assert len(ISLANDS) == 6
