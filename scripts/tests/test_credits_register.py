"""The credit file the app shows (`app/config/credits.yaml`) agrees with the register of external
sources in docs/specs/dependencies.md and with the licence files kept beside each copy of data.

These read across members (docs, app and each data package), so they live here and not in `app/`.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
REGISTER = ROOT / "docs" / "specs" / "dependencies.md"
CREDITS = ROOT / "app" / "config" / "credits.yaml"

# Each row of the register's "External sources" table, by its first column, and the credit
# entries that cover it. A row added to the register without an entry here fails the test below,
# which is the prompt to decide what credit the new source asks for.
REGISTER_ROWS = {
    "FAIRsharing": {"fairsharing"},
    "re3data": {"re3data"},
    "DataCite repositories": {"datacite-repositories"},
    "OpenAlex Sources (journals)": {"openalex"},
    "ROR": {"ror"},
    "DataCite and Crossref REST (works)": {"datacite-dois"},
    "ORCID public API": {"orcid"},
    "Crossref grants and the OpenAIRE Graph API v4 (projects)": {"openaire"},
    "Jisc Open Policy Finder, Crossref journals": {"open-policy-finder"},
    "Directory of Open Access Journals (DOAJ)": {"doaj"},
    "PRONOM": {"pronom"},
    "GA4GH Data Use Ontology (DUO)": {"duo"},
    "SPDX licence list": {"spdx"},
}


def _credits() -> list[dict[str, object]]:
    sources: list[dict[str, object]] = yaml.safe_load(CREDITS.read_text(encoding="utf-8"))[
        "sources"
    ]
    return sources


def _register_rows() -> list[str]:
    text = REGISTER.read_text(encoding="utf-8")
    section = text.split("### External sources", 1)[1].split("\n\n", 2)[1]
    rows = [line for line in section.splitlines() if line.startswith("|")][2:]
    return [row.split("|")[1].strip() for row in rows]


def test_every_source_in_the_register_has_a_credit() -> None:
    ids = {entry["id"] for entry in _credits()}
    rows = _register_rows()
    assert rows, "the register's table was not found"
    assert set(rows) == set(REGISTER_ROWS)
    for covered in REGISTER_ROWS.values():
        assert covered <= ids


def test_a_licence_file_beside_data_names_a_licence_the_credits_know() -> None:
    known = {entry["licence"] for entry in _credits()}
    names = {
        "CC-BY-SA-4.0": r"CC BY-SA 4\.0",
        "OGL-UK-3.0": r"Open Government Licence v3\.0",
        "CC-BY-4.0": r"CC BY 4\.0",
        "CC0-1.0": r"CC0",
    }
    checked = 0
    for path in ROOT.glob("*/src/*/data/LICENCE.md"):
        text = path.read_text(encoding="utf-8")
        mentioned = {licence for licence, pattern in names.items() if re.search(pattern, text)}
        assert mentioned & known, path
        checked += 1
    assert checked >= 4
