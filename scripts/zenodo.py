# /// script
# requires-python = ">=3.14"
# dependencies = ["pyyaml>=6.0"]
# ///
"""Archive a release of this repository in Zenodo, which gives it a DOI.

The repository has one Zenodo record. Its concept DOI does not change and always resolves to the
latest version; every release publishes a new version, with its own DOI. The record's metadata
comes from `CITATION.cff` and `.release-please-manifest.json`, so it is corrected there, not in
Zenodo.

    uv run scripts/zenodo.py create                       # once: make the draft, reserve its DOI
    uv run scripts/zenodo.py release --archive dd.zip     # each release: replace the file, publish
    uv run scripts/zenodo.py release --archive dd.zip --dry-run   # print the metadata, call nothing

`create` and `release` read a personal token from `ZENODO_TOKEN` (Zenodo, Applications, Personal
access tokens, with the scopes `deposit:write` and `deposit:actions`). `release` reads the record's
ID from `ZENODO_RECORD_ID`, which `create` prints. `ZENODO_API` overrides the API address, for
example `https://sandbox.zenodo.org/api` to rehearse. RELEASING.md describes the setup and the
workflow that runs this.
"""

from __future__ import annotations

import argparse
import datetime
import html
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
CITATION = ROOT / "CITATION.cff"
MANIFEST = ROOT / ".release-please-manifest.json"

DEFAULT_API = "https://zenodo.org/api"

# Zenodo's DataCite prefix, which a concept DOI shares with every version DOI.
DOI_PREFIX = "10.5281/zenodo."

# Seconds to wait for one API call or the upload.
TIMEOUT = 300


class ZenodoError(Exception):
    """A call to the API failed; the message says which and why."""


class Client:
    """The few Zenodo API calls this script needs, with the token in the header."""

    def __init__(self, api: str, token: str) -> None:
        self.api = api.rstrip("/")
        self.token = token

    def call(self, method: str, path: str, body: Any = None) -> Any:
        url = path if path.startswith(("https://", "http://")) else f"{self.api}{path}"
        data = None if body is None else json.dumps(body).encode()
        return self._send(method, url, data, "application/json")

    def put_bytes(self, url: str, data: bytes) -> Any:
        return self._send("PUT", url, data, "application/octet-stream")

    def _send(self, method: str, url: str, data: bytes | None, content_type: str) -> Any:
        request = urllib.request.Request(url, data=data, method=method)
        request.add_header("Authorization", f"Bearer {self.token}")
        request.add_header("Content-Type", content_type)
        request.add_header("Accept", "application/json")
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                text = response.read().decode()
        except urllib.error.HTTPError as error:
            detail = error.read().decode(errors="replace")
            raise ZenodoError(f"{method} {url} returned {error.code}: {detail}") from error
        except urllib.error.URLError as error:
            raise ZenodoError(f"{method} {url} failed: {error.reason}") from error
        return json.loads(text) if text else None


def read_citation() -> dict[str, Any]:
    with CITATION.open(encoding="utf-8") as stream:
        citation: dict[str, Any] = yaml.safe_load(stream)
    return citation


def components() -> dict[str, str]:
    """Each released package's version, by its path, from release-please's manifest."""
    versions: dict[str, str] = json.loads(MANIFEST.read_text(encoding="utf-8"))
    return versions


def creators(citation: dict[str, Any]) -> list[dict[str, str]]:
    """CITATION.cff's authors as Zenodo creators: "Family, Given", with ORCID and affiliation."""
    result = []
    for person in citation["authors"]:
        if "name" in person:
            creator = {"name": person["name"]}
        else:
            creator = {"name": f"{person['family-names']}, {person['given-names']}"}
        if orcid := person.get("orcid"):
            creator["orcid"] = orcid.removeprefix("https://orcid.org/")
        if affiliation := person.get("affiliation"):
            creator["affiliation"] = affiliation
        result.append(creator)
    return result


def description(citation: dict[str, Any], commit: str | None) -> str:
    """The abstract, then what this version contains: the commit and each package's version."""
    paragraphs = [html.escape(" ".join(citation["abstract"].split()))]
    if commit:
        tree = f"{citation['repository-code'].rstrip('/')}/tree/{commit}"
        paragraphs.append(
            f'This version archives commit <a href="{html.escape(tree)}">{commit[:12]}</a>.'
        )
    packages = ", ".join(f"{path} {version}" for path, version in sorted(components().items()))
    paragraphs.append(f"Package versions: {html.escape(packages)}.")
    return "".join(f"<p>{text}</p>" for text in paragraphs)


def related_identifiers(citation: dict[str, Any], commit: str | None) -> list[dict[str, str]]:
    code = citation["repository-code"].rstrip("/")
    identifiers = [
        {
            "identifier": f"{code}/tree/{commit}" if commit else code,
            "relation": "isSupplementTo",
            "resource_type": "software",
        }
    ]
    for reference in citation.get("references", []):
        if doi := reference.get("doi"):
            identifiers.append({"identifier": doi, "relation": "references"})
    return identifiers


def metadata(citation: dict[str, Any], commit: str | None) -> dict[str, Any]:
    """The record's metadata in Zenodo's deposit format."""
    today = datetime.datetime.now(datetime.UTC).date().isoformat()
    body: dict[str, Any] = {
        "upload_type": "software",
        "title": citation["title"],
        "description": description(citation, commit),
        "creators": creators(citation),
        "keywords": citation["keywords"],
        # Zenodo names licences by their SPDX identifier in lower case.
        "license": citation["license"].lower(),
        "access_right": "open",
        "publication_date": today,
        "related_identifiers": related_identifiers(citation, commit),
    }
    if commit:
        # The same name as the archive that zenodo.yml makes: the date and the short commit.
        body["version"] = f"{today}-{commit[:7]}"
    return body


def concept_doi(deposition: dict[str, Any]) -> str:
    return f"{DOI_PREFIX}{deposition['conceptrecid']}"


def create(client: Client, citation: dict[str, Any]) -> None:
    body = metadata(citation, None) | {"prereserve_doi": True}
    deposition = client.call("POST", "/deposit/depositions", {"metadata": body})
    doi = deposition["metadata"]["prereserve_doi"]["doi"]
    report(
        f"Created draft Zenodo record {deposition['id']}. Its first version will have the DOI"
        f" {doi}; the DOI for every version is {concept_doi(deposition)}.",
        f"Set the repository variable ZENODO_RECORD_ID to {deposition['id']} and add"
        f" `doi: {concept_doi(deposition)}` to CITATION.cff. Nothing is public until the first"
        " release publishes it.",
    )


def draft_for_release(client: Client, record: int) -> dict[str, Any]:
    """The draft to publish: the first one, if it was never published, or else a new version."""
    deposition: dict[str, Any] = client.call("GET", f"/deposit/depositions/{record}")
    if not deposition["submitted"]:
        return deposition
    # A new version is made from the latest; a draft left by a failed run is returned again.
    latest = client.call("GET", f"/records/{record}/versions/latest")
    versioned = client.call("POST", f"/deposit/depositions/{latest['id']}/actions/newversion")
    draft: dict[str, Any] = client.call("GET", versioned["links"]["latest_draft"])
    return draft


def release(
    client: Client, citation: dict[str, Any], record: int, archive: Path, commit: str
) -> None:
    draft = draft_for_release(client, record)
    path = f"/deposit/depositions/{draft['id']}"
    # A new version starts with the previous version's files; it holds only this release's.
    for file in client.call("GET", f"{path}/files"):
        client.call("DELETE", f"{path}/files/{file['id']}")
    name = urllib.parse.quote(archive.name)
    client.put_bytes(f"{draft['links']['bucket']}/{name}", archive.read_bytes())
    client.call("PUT", path, {"metadata": metadata(citation, commit)})
    published = client.call("POST", f"{path}/actions/publish")
    report(
        f"Published Zenodo record {published['id']}: https://doi.org/{published['doi']}"
        f" (every version: https://doi.org/{concept_doi(published)})."
    )


def report(*lines: str) -> None:
    """Print to the log and, in GitHub Actions, to the job summary."""
    for line in lines:
        print(line)
    if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(summary).open("a", encoding="utf-8") as stream:
            stream.write("\n\n".join(lines) + "\n")


def environment(name: str) -> str:
    if value := os.environ.get(name):
        return value
    raise ZenodoError(f"{name} is not set")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("create", help="make the draft record and reserve its DOI (once)")
    publish = commands.add_parser("release", help="publish a new version of the record")
    publish.add_argument("--archive", type=Path, required=True, help="the file to deposit")
    publish.add_argument("--commit", default=os.environ.get("GITHUB_SHA", ""), help="its commit")
    publish.add_argument("--dry-run", action="store_true", help="print the metadata and stop")
    args = parser.parse_args(argv)

    citation = read_citation()
    try:
        if args.command == "release" and args.dry_run:
            print(json.dumps(metadata(citation, args.commit or None), indent=2))
            return 0
        client = Client(os.environ.get("ZENODO_API") or DEFAULT_API, environment("ZENODO_TOKEN"))
        if args.command == "create":
            create(client, citation)
        else:
            if not args.archive.is_file():
                raise ZenodoError(f"{args.archive} does not exist")
            record = int(environment("ZENODO_RECORD_ID"))
            release(client, citation, record, args.archive, args.commit)
    except ZenodoError as error:
        print(f"zenodo: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
