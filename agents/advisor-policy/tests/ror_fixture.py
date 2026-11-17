"""A ROR registry built from the committed fixture: nine organisations cut from ROR dump v2.15
(2026-10-20, CC0), through the same `ror.build` path as the real one. It holds the Natural
Environment Research Council and the two National Energy Research Centers that share its acronym,
the two organisations called ESRC, both called UKRI, Wellcome, and one inactive organisation."""

from __future__ import annotations

from pathlib import Path

from dd_agent_advisor_policy import ror
from dd_sdk.registry import pinned

FIXTURE = Path(__file__).with_name("data") / "ror-dump-fixture.zip"
NERC = "https://ror.org/02b5d8509"
NERC_JO = "https://ror.org/015byt818"
NERC_SD = "https://ror.org/039m4k502"
UKRI = "https://ror.org/001aqnf71"
INACTIVE = "https://ror.org/01952nm43"


def build_fixture(directory: Path) -> ror.RorDump:
    built = pinned.install(directory, ror.build(FIXTURE), FIXTURE)
    ror.Pin(
        version="v2.15",
        archive="https://zenodo.org/records/23500708/files/v2.15-2026-10-20-ror-data.zip",
        archive_sha256=built.archive_sha256,
        doi="https://doi.org/10.5281/zenodo.23500708",
        records=built.records,
        snapshot_sha256=built.snapshot_sha256,
        fetched_at="2026-11-15T00:00:00+00:00",
    ).write(directory / "manifest.json")
    return ror.RorDump(built.path, directory / "manifest.json")
