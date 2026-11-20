"""ORCID iDs, resolved through ORCID's public API (https://info.orcid.org/documentation/features/public-api/).

Only what the person has made public is read, from the iD's `person` section, and only the name is
kept: an iD resolves to who it is, not to what they have done. The public API needs no account for
reading single records.
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ConfigDict

from dd_mcp_pid.http import Http, UnavailableError

ORCID_API = "https://pub.orcid.org/v3.0"
ORCID_URL = "https://orcid.org/"
ORCID_ID = re.compile(r"^(?:https?://orcid\.org/)?(\d{4}-\d{4}-\d{4}-\d{3}[\dX])/?$", re.IGNORECASE)


def checksum_ok(digits: str) -> bool:
    """ISO 7064 MOD 11-2, as ORCID computes its last character."""
    total = 0
    for ch in digits[:-1]:
        total = (total + int(ch)) * 2
    check = (12 - total % 11) % 11
    return digits[-1] == ("X" if check == 10 else str(check))


def orcid_url(value: str) -> str | None:
    """`value` as an ORCID iD URL with a valid check character, or None."""
    found = ORCID_ID.match(value.strip())
    if not found:
        return None
    bare = found.group(1).upper()
    return f"{ORCID_URL}{bare}" if checksum_ok(bare.replace("-", "")) else None


class OrcidRecord(BaseModel):
    """A person as their public ORCID record names them. Every name is None when the person keeps
    it private."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    orcid: str
    """The iD as a URL: what the record is cited by."""
    given_names: str | None = None
    family_name: str | None = None
    credit_name: str | None = None

    def document(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


def _value(name: dict[str, Any], key: str) -> str | None:
    found = (name.get(key) or {}).get("value")
    return found if isinstance(found, str) and found.strip() else None


class Orcid:
    """ORCID's public API."""

    def __init__(self, http: Http | None = None) -> None:
        self.http = http or Http("ORCID", headers={"Accept": "application/vnd.orcid+json"})

    def get(self, url: str) -> OrcidRecord | None:
        """The public record of the iD (an `orcid_url`), or None when ORCID has no such iD."""
        bare = url.removeprefix(ORCID_URL)
        resp = self.http.get(f"{ORCID_API}/{bare}/person")
        if resp.status_code == 404:
            return None
        if resp.status_code != 200:
            raise UnavailableError(f"ORCID: HTTP {resp.status_code}")
        try:
            name = self.http.json(resp).get("name") or {}
            return OrcidRecord(
                orcid=url,
                given_names=_value(name, "given-names"),
                family_name=_value(name, "family-name"),
                credit_name=_value(name, "credit-name"),
            )
        except (TypeError, AttributeError, ValueError) as exc:
            raise UnavailableError(f"ORCID: an answer that cannot be read ({exc})") from None
