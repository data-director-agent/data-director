"""Names re3data does not list, read through `aliases.yaml` (#1233)."""

from __future__ import annotations

import re

import yaml

from dd_agent_advisor_repository import aliases


def test_every_alias_names_a_re3data_record_and_gives_its_source() -> None:
    data = yaml.safe_load(aliases.ALIASES.read_text(encoding="utf-8"))
    for entry in data["aliases"]:
        assert re.fullmatch(r"r3d[0-9]{9}", entry["re3data_id"]), entry
        assert entry["source"].startswith("https://"), entry
        assert entry["names"], entry


def test_reshare_is_the_uk_data_service_whatever_its_case() -> None:
    for name in ("ReShare", "UK Data Service ReShare", "  ukds reshare "):
        assert aliases.re3data_id(name) == "r3d100010230"


def test_a_name_not_in_the_list_is_none() -> None:
    assert aliases.re3data_id("Zenodo") is None
