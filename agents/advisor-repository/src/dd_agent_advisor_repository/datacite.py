"""The repositories DataCite registers that re3data does not list, from a committed snapshot.

re3data lists only some of the institutional repositories researchers deposit in. Every
repository that mints DataCite DOIs is registered with DataCite as a repository of one of its
members, and DataCite publishes those records through its REST API, openly and under CC0
(https://support.datacite.org/docs/api). Each names its member, whose record carries the member's
ROR identifier, so a repository can be matched to the researcher's institution by ROR.

`dd-datacite fetch` keeps a repository when DataCite marks it active, as a repository rather than
a periodical, it links to no re3data record (re3data describes those, with more facts), and it has
registered at least one DOI of resource type Dataset, which tells a data repository from a press
or a theses service, both of which DataCite also types as institutional. The snapshot is committed
beside `manifest.json`, which pins its SHA-256, as the FAIRsharing snapshot is: DataCite publishes
no archive that could be fetched again to the same bytes. Both `sources.yaml` files pin the same
hash, so the harness's source check verifies every DataCite evidence item against it
(docs/specs/grounding.md).

`Registries` puts the two registries behind the one `Repositories` seam the agent reads: re3data
answers searches by theme, both answer names and identifiers, and DataCite adds the repositories
of the researcher's own institution.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import cached_property
from pathlib import Path
from typing import Any

import httpx

from dd_agent_advisor_repository import assess
from dd_agent_advisor_repository.classes import Affiliation
from dd_agent_advisor_repository.records import DataciteRecord, Re3dataRecord
from dd_agent_advisor_repository.snapshot import Re3dataRegistry
from dd_sdk.registry import Hit, Query, RegistryUnavailable, SnapshotRef
from dd_sdk.registry import pinned

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "datacite"
SNAPSHOT = DATA_DIR / "repositories.jsonl"
MANIFEST = DATA_DIR / "manifest.json"

API = "https://api.datacite.org"
CITATION = "DataCite REST API, repositories and providers. https://support.datacite.org/docs/api"
LICENCE = "CC0 1.0 (DataCite metadata); see SOURCE.md"
FETCH_COMMAND = "uv run dd-datacite fetch"
TIMEOUT_S = 120.0
PAGE_SIZE = 1000
# DataCite's facets give the ten largest values, so the datasets of ten repositories are counted
# in one request.
COUNT_BATCH = 10


class DataciteError(pinned.PinError):
    """The snapshot cannot be fetched or read as pinned. The message says what to do."""


@dataclass(frozen=True)
class Pin:
    fetched_at: str
    source: str
    records: int
    sha256: str
    citation: str = CITATION
    licence: str = LICENCE

    @property
    def label(self) -> str:
        """The evidence's `snapshot_ref` for records from this snapshot."""
        return f"datacite:repositories:{self.fetched_at[:10]}"

    @property
    def credit(self) -> str:
        return (
            "Repositories re3data does not list are from DataCite's registry of repositories "
            f"(fetched {self.fetched_at[:10]}, CC0; https://support.datacite.org/docs/api)."
        )

    @classmethod
    def load(cls, path: Path = MANIFEST) -> Pin:
        return pinned.read_pin(cls, path, "DataCite", DataciteError)

    def write(self, path: Path = MANIFEST) -> None:
        pinned.write_pin(self, path)


def _user_agent() -> str:
    """Names the project and where to find it, never a person."""
    return pinned.user_agent(
        "data-director-agent-advisor-repository", "data-director-advisor-repository"
    )


# --- fetching ------------------------------------------------------------------------------------


def _pages(http: httpx.Client) -> Iterator[dict[str, Any]]:
    """Every page of DataCite's repositories, each with the members it names."""
    number = 1
    while True:
        response = http.get(
            f"{API}/repositories",
            params={"page[size]": PAGE_SIZE, "page[number]": number, "include": "provider"},
        )
        response.raise_for_status()
        page = response.json()
        yield page
        if number >= int(page.get("meta", {}).get("totalPages", 1)):
            return
        number += 1


def _kept(entry: dict[str, Any]) -> bool:
    a = entry.get("attributes", {})
    return bool(a.get("isActive")) and a.get("clientType") == "repository" and not a.get("re3data")


def _datasets(http: httpx.Client, ids: list[str]) -> dict[str, int]:
    """How many DOIs of resource type Dataset each repository of `ids` has registered."""
    counts: dict[str, int] = {}
    for start in range(0, len(ids), COUNT_BATCH):
        batch = ids[start : start + COUNT_BATCH]
        # Commas literally: DataCite does not split an encoded list.
        response = http.get(
            f"{API}/dois?resource-type-id=dataset&page[size]=0&disable-facets=false"
            f"&facets=clients&client-id={','.join(batch)}"
        )
        response.raise_for_status()
        for facet in response.json().get("meta", {}).get("clients") or []:
            counts[str(facet["id"])] = int(facet["count"])
    return counts


def _record(entry: dict[str, Any], members: dict[str, Any], datasets: int) -> DataciteRecord:
    a = entry["attributes"]
    rel = entry.get("relationships", {})
    member = members.get(rel.get("provider", {}).get("data", {}).get("id"), {})
    return DataciteRecord(
        datacite_id=entry["id"],
        name=a["name"],
        alternate_name=a.get("alternateName") or None,
        url=a.get("url") or None,
        repository_types=a.get("repositoryType") or [],
        software=a.get("software") or None,
        certificates=a.get("certificate") or [],
        opendoar=str(a["opendoar"]) if a.get("opendoar") else None,
        dataset_count=datasets,
        prefixes=[p["id"] for p in rel.get("prefixes", {}).get("data") or []],
        member={
            "name": member.get("name"),
            "ror": member.get("rorId") or None,
            "country": member.get("country") or None,
            "organization_type": member.get("organizationType") or None,
        },
    )


def records(http: httpx.Client) -> list[DataciteRecord]:
    """The repositories kept (module docstring), sorted by identifier."""
    entries: list[dict[str, Any]] = []
    members: dict[str, Any] = {}
    for page in _pages(http):
        entries += [e for e in page.get("data", []) if _kept(e)]
        members |= {m["id"]: m["attributes"] for m in page.get("included", [])}
    counts = _datasets(http, sorted(e["id"] for e in entries))
    kept = [_record(e, members, counts[e["id"]]) for e in entries if counts.get(e["id"], 0) > 0]
    return sorted(kept, key=lambda r: r.datacite_id)


def build(found: list[DataciteRecord]) -> bytes:
    """The snapshot's bytes: one record document per line, as hashed (`records.py`)."""
    return "".join(
        json.dumps(r.document(), sort_keys=True, ensure_ascii=False) + "\n" for r in found
    ).encode("utf-8")


def fetch(
    *,
    snapshot: Path = SNAPSHOT,
    manifest: Path = MANIFEST,
    client: httpx.Client | None = None,
    now: datetime | None = None,
) -> Pin:
    """Fetch the repositories anew, write the snapshot and pin it."""
    http = client or httpx.Client(
        timeout=TIMEOUT_S, headers={"User-Agent": _user_agent()}, follow_redirects=True
    )
    try:
        data = build(records(http))
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        raise DataciteError(f"DataCite could not be read: {exc}") from None
    finally:
        if client is None:
            http.close()
    pinned.write_atomic(snapshot, data)
    pin = Pin(
        fetched_at=(now or datetime.now(UTC)).isoformat(timespec="seconds"),
        source=f"{API}/repositories",
        records=data.count(b"\n"),
        sha256=hashlib.sha256(data).hexdigest(),
    )
    pin.write(manifest)
    return pin


def main(argv: Sequence[str] | None = None) -> int:
    """Console script `dd-datacite`."""
    parser = argparse.ArgumentParser(prog="dd-datacite", description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("fetch", help="fetch DataCite's repositories anew and pin the snapshot")
    sub.add_parser("check", help="exit 1 unless the snapshot matches its pin")
    args = parser.parse_args(argv)
    if args.command == "check":
        return pinned.check(problem(), "DataCite snapshot matches its pin")
    try:
        pin = fetch()
    except DataciteError as exc:
        sys.stderr.write(f"dd-datacite: {exc}\n")
        return 1
    sys.stdout.write(
        f"DataCite repositories fetched {pin.fetched_at}: {pin.records} kept.\n"
        f"sha256 {pin.sha256}; update both sources.yaml pins (snapshot_ref {pin.label}).\n"
    )
    return 0


def problem(snapshot: Path = SNAPSHOT, manifest: Path = MANIFEST) -> str | None:
    """Why the snapshot cannot be used as pinned, or None when it can."""
    try:
        pin = Pin.load(manifest)
    except DataciteError as exc:
        return str(exc)
    if not snapshot.is_file():
        return f"the DataCite snapshot is missing at {snapshot}; run `{FETCH_COMMAND}`"
    if pinned.sha256_file(snapshot) != pin.sha256:
        return f"the DataCite snapshot at {snapshot} does not match its pin; run `{FETCH_COMMAND}`"
    return None


# --- reading -------------------------------------------------------------------------------------


class DataciteRegistry:
    """The committed snapshot, checked against its pin when first read."""

    def __init__(self, path: Path = SNAPSHOT, manifest: Path = MANIFEST) -> None:
        self.path = path
        self.manifest = manifest

    @cached_property
    def pin(self) -> Pin:
        try:
            return Pin.load(self.manifest)
        except DataciteError as exc:
            raise RegistryUnavailable(str(exc)) from None

    @cached_property
    def records(self) -> list[DataciteRecord]:
        if (found := problem(self.path, self.manifest)) is not None:
            raise RegistryUnavailable(found)
        with self.path.open(encoding="utf-8") as fh:
            return [DataciteRecord.model_validate_json(line) for line in fh if line.strip()]

    @cached_property
    def _by_id(self) -> dict[str, DataciteRecord]:
        return {r.datacite_id: r for r in self.records}

    def snapshot_ref(self) -> SnapshotRef:
        return SnapshotRef(label=self.pin.label, fetched_at=self.pin.fetched_at)

    def fetch(self, datacite_id: str) -> DataciteRecord | None:
        return self._by_id.get(datacite_id)

    def find(self, name: str) -> list[DataciteRecord]:
        """The repositories named `name`, ignoring case, by name and then by alternate name."""
        wanted = name.casefold().strip()
        named = [r for r in self.records if r.name.casefold().strip() == wanted]
        return named or [r for r in self.records if wanted in r.names()]

    def institutional(self, affiliation: Affiliation | None) -> list[DataciteRecord]:
        """The repositories whose member is the researcher's institution (`assess.affiliated`)."""
        return [r for r in self.records if assess.affiliated(r, affiliation) is not None]


Record = Re3dataRecord | DataciteRecord


def _address(url: str | None) -> str | None:
    """A web address without its scheme, `www.`, case or trailing slash, to tell when two
    registries describe the same repository."""
    if not url:
        return None
    bare = url.strip().lower().split("://", 1)[-1].removeprefix("www.")
    return bare.rstrip("/") or None


class Registries:
    """re3data and DataCite behind the one `Repositories` seam. re3data answers alone where it
    can: searches by theme and subject, and every name it lists; DataCite answers a name re3data
    does not list, its own identifiers, and the researcher's own institution's repositories. A
    DataCite record whose address is a re3data record's is that record, which re3data describes
    with more facts, even where DataCite does not link the two; it is left out."""

    def __init__(self, re3data: Re3dataRegistry, datacite: DataciteRegistry) -> None:
        self.re3data = re3data
        self.datacite = datacite

    @cached_property
    def _listed(self) -> frozenset[str]:
        return frozenset(a for r in self.re3data.records if (a := _address(r.url)) is not None)

    def _unlisted(self, found: list[DataciteRecord]) -> list[DataciteRecord]:
        return [r for r in found if _address(r.url) not in self._listed]

    def snapshot_ref(self) -> SnapshotRef:
        return self.re3data.snapshot_ref()

    def snapshot_of(self, record: Record) -> SnapshotRef:
        """The copy a record was read from, for its evidence."""
        if isinstance(record, DataciteRecord):
            return self.datacite.snapshot_ref()
        return self.re3data.snapshot_ref()

    def credit(self) -> str:
        return f"{self.re3data.credit()} {self.datacite.pin.credit}"

    def search(self, query: Query) -> list[Hit[Re3dataRecord]]:
        return self.re3data.search(query)

    def fetch(self, repository_id: str) -> Any:
        if repository_id.startswith("r3d"):
            return self.re3data.fetch(repository_id)
        found = self.datacite.fetch(repository_id)
        return next(iter(self._unlisted([found])), None) if found is not None else None

    def subjects(self) -> dict[str, str]:
        return self.re3data.subjects()

    def with_subject(self, code: str) -> list[Re3dataRecord]:
        return self.re3data.with_subject(code)

    def find(self, name: str) -> list[Any]:
        return self.re3data.find(name) or self._unlisted(self.datacite.find(name))

    def institutional(self, affiliation: Affiliation | None) -> list[Any]:
        return self._unlisted(self.datacite.institutional(affiliation))
