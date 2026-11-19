"""The cost check dry-runs every compiled model and flags those above the byte budget."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from google.cloud import bigquery

from hurricane_loaders.cost_check import check, main


def manifest(tmp_path: Path) -> Path:
    nodes = {
        "model.p.small": {"resource_type": "model", "name": "small", "compiled_code": "select 1"},
        "model.p.big": {"resource_type": "model", "name": "big", "compiled_code": "select 2"},
        "test.p.t": {"resource_type": "test", "name": "t", "compiled_code": "select 3"},
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps({"nodes": nodes}))
    return path


def client(bytes_by_sql: dict[str, int]) -> MagicMock:
    bq = MagicMock(spec=bigquery.Client)
    bq.query.side_effect = lambda sql, job_config: MagicMock(
        total_bytes_processed=bytes_by_sql[sql]
    )
    return bq


def test_models_over_budget_are_returned(tmp_path: Path) -> None:
    bq = client({"select 1": 10_000_000, "select 2": 300_000_000})
    assert check(manifest(tmp_path), bq, 200_000_000) == [("big", 300_000_000)]
    for call in bq.query.call_args_list:
        assert call.kwargs["job_config"].dry_run is True  # a dry run bills nothing
    assert bq.query.call_count == 2  # tests are not models


def test_main_fails_when_a_model_is_over_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bq = client({"select 1": 10_000_000, "select 2": 300_000_000})
    monkeypatch.setattr("hurricane_loaders.cost_check.bigquery.Client", lambda project: bq)
    with pytest.raises(SystemExit) as exit_info:
        main([str(manifest(tmp_path)), "--budget-mb", "200"])
    assert exit_info.value.code == 1
