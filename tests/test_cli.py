"""The command line refuses what it cannot do instead of doing nothing quietly."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from hurricane_loaders.cli import main


def test_since_is_only_for_weather(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["tracks", "--since", "2020-01-01"])
    assert exit_info.value.code == 2
    assert "--since" in capsys.readouterr().err


def test_since_after_the_last_available_day_is_an_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    future = (date.today() + timedelta(days=1)).isoformat()
    with pytest.raises(SystemExit) as exit_info:
        main(["weather", "--since", future])
    assert exit_info.value.code == 2
    assert "after the last day" in capsys.readouterr().err
