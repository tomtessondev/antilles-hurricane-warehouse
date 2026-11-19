"""Every dbt query is capped: a mistake fails instead of billing."""

from __future__ import annotations

from pathlib import Path

import yaml

PROFILES = Path(__file__).resolve().parents[1] / "profiles.yml"


def test_profiles_cap_bytes_billed() -> None:
    outputs = yaml.safe_load(PROFILES.read_text())["antilles_hurricanes"]["outputs"]
    assert outputs
    assert all(o["maximum_bytes_billed"] == 1_000_000_000 for o in outputs.values())
    assert all(o["location"] == "US" for o in outputs.values())


def test_pull_requests_have_their_own_dataset() -> None:
    outputs = yaml.safe_load(PROFILES.read_text())["antilles_hurricanes"]["outputs"]
    assert outputs["ci"]["dataset"] == "ci"
    assert outputs["prod"]["dataset"] != "ci"
