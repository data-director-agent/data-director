"""The journal registry is declared as a built source, so `dd-sources prepare` builds it."""

from __future__ import annotations

from pathlib import Path

import pytest

from dd_agent_advisor_policy import journals_source
from dd_journals import PinError
from dd_journals.snapshot import Pin
from dd_sdk.sources import SourceBuildError


def test_the_journal_registry_is_declared_as_a_built_source() -> None:
    assert journals_source.SOURCE.name == "journals"
    assert journals_source.SOURCE.pin() == Pin.load().registry_sha256


def test_a_build_that_fails_is_a_source_build_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def fails(cache_dir: Path) -> Pin:
        raise PinError("cannot download")

    monkeypatch.setattr(journals_source, "fetch", fails)
    with pytest.raises(SourceBuildError, match="journals"):
        journals_source.SOURCE.prepare(tmp_path)
