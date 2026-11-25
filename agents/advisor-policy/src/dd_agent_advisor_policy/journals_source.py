"""The journal registry (`dd-journals`) as a source built outside git (dd_sdk.sources), so that
`dd-sources prepare` builds it, and its index, with the other sources. The PID resolver's
`journals` server reads it; the policy advisor will identify journals from it (#1514).
`dd-journals` itself uses nothing of the Data Director's own, so it is registered here."""

from __future__ import annotations

from pathlib import Path

from dd_journals import PinError
from dd_journals.snapshot import ARCHIVES, Pin, fetch, problem
from dd_sdk.sources import BuiltSource, SourceBuildError


def _prepare(cache_dir: Path | None) -> None:
    try:
        fetch(cache_dir=cache_dir or ARCHIVES)
    except PinError as exc:
        raise SourceBuildError(f"journals: {exc}") from None


def _pin() -> str:
    try:
        return Pin.load().registry_sha256
    except PinError as exc:
        raise SourceBuildError(str(exc)) from None


# Registered under the `dd.sources` entry point (pyproject.toml).
SOURCE = BuiltSource(name="journals", pin=_pin, problem=lambda: problem(), prepare=_prepare)
