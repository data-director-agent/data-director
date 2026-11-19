"""Names re3data's records do not list, read through `aliases.yaml` (#1233).

A data management plan may name a repository by a service's name, such as "ReShare" for the UK
Data Service's self-deposit repository, that re3data's record does not give as a name or an
alias. Such a name is looked up here only when re3data's own names find nothing; the record it
leads to is still fetched from re3data and grounds the candidate, and the outcome says the name
was read through this list.
"""

from __future__ import annotations

from functools import cache
from pathlib import Path

import yaml

ALIASES = Path(__file__).with_name("aliases.yaml")


@cache
def table() -> dict[str, str]:
    """Each alias, casefolded, with the re3data identifier it names."""
    data = yaml.safe_load(ALIASES.read_text(encoding="utf-8"))
    return {
        name.casefold().strip(): entry["re3data_id"]
        for entry in data["aliases"]
        for name in entry["names"]
    }


def re3data_id(name: str) -> str | None:
    """The re3data identifier `name` is an alias of, or None."""
    return table().get(name.casefold().strip())
