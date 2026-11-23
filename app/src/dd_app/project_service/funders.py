"""The funders a project's facts name, looked up in the pinned ROR dump."""

from __future__ import annotations

from typing import Any

from dd_app.project_service._area import Area

ROR_PAGE = "https://ror.org/"
# The DOI prefix of every Crossref Funder ID.
CROSSREF_FUNDER_PREFIX = "10.13039/"


class UnknownOrganisationError(LookupError):
    """The pinned ROR dump holds no organisation at this identifier."""


def crossref_funder_doi(funder_id: str) -> str:
    """`funder_id`, a Crossref Funder ID with or without its DOI prefix, as a doi.org address."""
    bare = funder_id.removeprefix(CROSSREF_FUNDER_PREFIX)
    return f"https://doi.org/{CROSSREF_FUNDER_PREFIX}{bare}"


class Funders(Area):
    def organisation(self, ror_id: str) -> dict[str, Any]:
        """The organisation the latest pinned ROR dump holds at `ror_id`, as the dump records it,
        with the dump it was read from and the addresses that identify it. Raises
        `SourceConfigError` if no dump is pinned and built, and `UnknownOrganisationError` if the
        dump holds no organisation at `ror_id`."""
        snapshot_ref, record = self.governance.conductor.sources.organisation(ror_id)
        if record is None:
            raise UnknownOrganisationError(f"{snapshot_ref} holds no organisation {ror_id!r}.")
        return {
            "snapshot_ref": snapshot_ref,
            "ror_id": record["id"],
            "names": record["names"],
            "types": record["types"],
            "status": record["status"],
            "country_codes": record["country_codes"],
            "crossref_funder_ids": record["crossref_funder_ids"],
            "crossref_funder_preferred": record.get("crossref_funder_preferred"),
            "parents": record["parents"],
            "links": {
                "ror": record["id"],
                "crossref_funders": [crossref_funder_doi(i) for i in record["crossref_funder_ids"]],
            },
        }
