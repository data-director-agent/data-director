"""ROR identifiers and names, resolved from a built ROR registry or ROR's REST API.

ROR (https://ror.org) publishes each data dump on Zenodo under CC0
(https://doi.org/10.5281/zenodo.6347574). A *registry* here is one `Organisation` document per
line, built from one dump; the Data Director's policy advisor builds and pins it (`dd-ror fetch`).
`RorIndex` reads such a file; `RorApi` asks `api.ror.org/v2`, which needs no account. Both give the
same `Organisation` for the same organisation.

A name is matched exactly, ignoring case and spacing, against every name ROR records for an
organisation (labels, acronyms and aliases); only active organisations are matched by name.
"""

from __future__ import annotations

import json
from functools import cached_property
from pathlib import Path

from pydantic import ValidationError

from dd_mcp_pid.http import Http, UnavailableError
from dd_mcp_pid.ror_records import ACTIVE, ROR_URL, Organisation, from_ror_json, normalise, ror_url

API_BASE = "https://api.ror.org/v2/organizations"


class RorIndex:
    """A built registry. Lines are parsed only when a name or an identifier picks them out, so
    the whole registry is never held as objects. Raises `UnavailableError` if the file is
    missing."""

    def __init__(self, path: Path) -> None:
        self.path = path

    @cached_property
    def _lines(self) -> list[str]:
        try:
            with self.path.open(encoding="utf-8") as fh:
                return [line for line in fh if line.strip()]
        except OSError as exc:
            raise UnavailableError(f"ROR registry {self.path}: {exc.strerror or exc}") from None

    @cached_property
    def _index(self) -> tuple[dict[str, list[int]], dict[str, int]]:
        by_name: dict[str, list[int]] = {}
        by_id: dict[str, int] = {}
        for i, line in enumerate(self._lines):
            doc = json.loads(line)
            by_id[doc["id"]] = i
            if doc.get("status") != ACTIVE:
                continue
            for name in {normalise(n["value"]) for n in doc.get("names") or []}:
                by_name.setdefault(name, []).append(i)
        return by_name, by_id

    def _at(self, i: int) -> Organisation:
        return Organisation.model_validate(json.loads(self._lines[i]))

    def find(self, name: str) -> list[Organisation]:
        """The active organisations with this name, acronym or alias, by identifier."""
        by_name, _ = self._index
        return sorted((self._at(i) for i in by_name.get(normalise(name), [])), key=lambda o: o.id)

    def get(self, ror_id: str) -> Organisation | None:
        """The organisation with this identifier (a URL or bare), whatever its status."""
        url = ror_url(ror_id)
        _, by_id = self._index
        return self._at(by_id[url]) if url and url in by_id else None


class RorApi:
    """ROR's REST API. Any transport failure, or an answer that cannot be read, raises
    `UnavailableError`."""

    def __init__(self, http: Http | None = None) -> None:
        self.http = http or Http("ROR")

    def find(self, name: str) -> list[Organisation]:
        """The active organisations with this name, acronym or alias, from the first page of
        ROR's search, by identifier."""
        resp = self.http.get(API_BASE, {"query": name})
        if resp.status_code != 200:
            raise UnavailableError(f"ROR: HTTP {resp.status_code} for a search")
        try:
            found = [from_ror_json(item) for item in self.http.json(resp).get("items") or []]
        except (KeyError, TypeError, AttributeError, ValidationError) as exc:
            raise UnavailableError(f"ROR: an answer that cannot be read ({exc})") from None
        unique = {o.id: o for o in found if o.active and o.matches(name)}
        return [unique[k] for k in sorted(unique)]

    def get(self, ror_id: str) -> Organisation | None:
        """The organisation with this identifier (a URL or bare), whatever its status."""
        url = ror_url(ror_id)
        if url is None:
            return None
        resp = self.http.get(f"{API_BASE}/{url.removeprefix(ROR_URL)}")
        if resp.status_code == 404:
            return None
        if resp.status_code != 200:
            raise UnavailableError(f"ROR: HTTP {resp.status_code} for {url}")
        try:
            return from_ror_json(self.http.json(resp))
        except (KeyError, TypeError, AttributeError, ValidationError) as exc:
            raise UnavailableError(f"ROR: an answer that cannot be read ({exc})") from None
