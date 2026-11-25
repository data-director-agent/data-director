"""The credit each external source asks for, read from `app/config/credits.yaml`.

`GET /api/sources` serves it, the "Sources and licences" page draws it, and the evidence panel
names an item's source by matching `match` against the item's `source_id` and `snapshot_ref`.
The file is a list of facts about other people's terms, not a policy: it enforces nothing, and a
deployment's policy choices live in its profile (AGENTS.md).
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict

from dd_app.config import CONFIG_DIR

DEFAULT_CREDITS = CONFIG_DIR / "credits.yaml"


class Match(BaseModel):
    """What marks an evidence item as from a source."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id_prefixes: list[str] = []
    snapshot_ref_prefixes: list[str] = []


class Credit(BaseModel):
    """One source, with the credit it asks for and the terms it sets."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    name: str
    url: str
    kind: Literal["data", "service", "font"]
    licence: str
    licence_url: str
    attribution: str
    credit_required: bool
    non_commercial: bool
    use: Literal["pinned", "live", "both"]
    terms_url: str | None = None
    citation: str | None = None
    badge_url: str | None = None
    match: Match = Match()


def load(path: Path = DEFAULT_CREDITS) -> list[Credit]:
    """The credits in `path`. A malformed file is a configuration error, so it raises."""
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    credits = [Credit.model_validate(entry) for entry in document["sources"]]
    ids = [credit.id for credit in credits]
    if len(set(ids)) != len(ids):
        raise ValueError(f"{path}: a source id is used twice")
    return credits
