"""The ROR registry as a source built outside git (dd_sdk.sources), so that `dd-sources prepare`
builds it without anything else knowing how. Kept apart from `ror.py`, which uses nothing of the
Data Director's own."""

from __future__ import annotations

from pathlib import Path

from dd_agent_advisor_policy import ror
from dd_sdk.sources import BuiltSource, SourceBuildError


def _prepare(cache_dir: Path | None) -> None:
    try:
        ror.fetch(cache_dir=cache_dir or ror.ARCHIVES)
    except ror.RorError as exc:
        raise SourceBuildError(f"ror: {exc}") from None


def _pin() -> str:
    try:
        return ror.Pin.load().archive_sha256
    except ror.RorError as exc:
        raise SourceBuildError(str(exc)) from None


# Registered under the `dd.sources` entry point (pyproject.toml).
SOURCE = BuiltSource(name="ror", pin=_pin, problem=lambda: ror.problem(), prepare=_prepare)
