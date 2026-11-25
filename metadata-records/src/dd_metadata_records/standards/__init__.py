"""The definitions this library ships, each registered by entry point under its identifier."""

from __future__ import annotations

from pathlib import Path
from typing import Final

from dd_metadata_records.definition import load

HERE: Final = Path(__file__).resolve().parent

DATACITE_4: Final = load(HERE / "datacite-4.yaml")
DUBLIN_CORE_OAI: Final = load(HERE / "dublin-core-oai.yaml")
