"""Shared fixtures.

Sockets are disabled for the whole suite via `--disable-socket` in `pyproject.toml`'s
`addopts`, not by a fixture. That is deliberate: as an option it applies to every test whether
or not its author remembered, so an accidental call to a real model API is a test failure rather
than a surprise on someone's bill.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from standards_advisor.models.inputs import DatasetInput
from standards_advisor.settings import Settings, load_settings

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_CSV = PROJECT_ROOT / "samples" / "soil-chemistry.csv"
SAMPLE_METADATA = PROJECT_ROOT / "samples" / "soil-chemistry.metadata.json"


@pytest.fixture
def project_root() -> Path:
    return PROJECT_ROOT


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Real prompts, weights and schemas; a throwaway runs directory.

    The prompt library and weights file are the committed ones on purpose — a test that stubbed
    them would not notice a prompt whose hash no longer matches its manifest entry, which is one
    of the things the versioning discipline exists to catch.
    """
    return load_settings({}, project_root=PROJECT_ROOT, runs_root=tmp_path / "runs")


@pytest.fixture
def sample_input() -> DatasetInput:
    return DatasetInput(
        files=[str(SAMPLE_CSV)],
        metadata_path=str(SAMPLE_METADATA),
    )
