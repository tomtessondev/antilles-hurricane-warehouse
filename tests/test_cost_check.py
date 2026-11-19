"""The cost check dry-runs every compiled model and flags those above the byte budget."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from google.api_core.exceptions import NotFound
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


def test_models_whose_parents_are_not_built_yet_are_skipped(tmp_path: Path) -> None:
    """A pull request that adds a model: its parent tables exist only after the merge, so
    BigQuery cannot plan it yet. That is not a cost problem."""
    bq = MagicMock(spec=bigquery.Client)

    def dry_run(sql: str, job_config: bigquery.QueryJobConfig) -> MagicMock:
        if sql == "select 2":
            raise NotFound("Table antilles-hurricanes:marts.new_parent was not found")
        return MagicMock(total_bytes_processed=10_000_000)

    bq.query.side_effect = dry_run
    assert check(manifest(tmp_path), bq, 200_000_000) == []


def test_nodes_without_compiled_code_are_skipped(tmp_path: Path) -> None:
    path = manifest(tmp_path)
    data = json.loads(path.read_text())
    del data["nodes"]["model.p.big"]["compiled_code"]
    path.write_text(json.dumps(data))
    bq = client({"select 1": 10_000_000})
    assert check(path, bq, 200_000_000) == []
