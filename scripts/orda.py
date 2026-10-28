# /// script
# requires-python = ">=3.14"
# dependencies = ["pyyaml>=6.0"]
# ///
"""Archive a release of this repository in ORDA, the University of Sheffield's Figshare repository.

The repository has one ORDA item. Its DOI is reserved once and does not change; every release
publishes a new version of the item, with its own DOI ending `.v<N>`. The item's metadata comes
from `CITATION.cff` and `.release-please-manifest.json`, so it is corrected there, not in ORDA.

    uv run scripts/orda.py create                       # once: make the private item, reserve its DOI
    uv run scripts/orda.py release --archive dd.zip     # each release: replace the files, publish
    uv run scripts/orda.py release --archive dd.zip --dry-run   # print the metadata, call nothing

`create` and `release` read a personal token from `ORDA_TOKEN` (ORDA, Applications, Create
Personal Token). `release` reads the item's ID from `ORDA_ARTICLE_ID`, which `create` prints.
`ORDA_API` overrides the API address, for example to rehearse on a Figshare test instance.
RELEASING.md describes the setup and the workflow that runs this.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
CITATION = ROOT / "CITATION.cff"
MANIFEST = ROOT / ".release-please-manifest.json"

# ORDA's institutional accounts use the Figshare API.
DEFAULT_API = "https://api.figshare.com/v2"

# ANZSRC Fields of Research (2020) codes, which Figshare accepts as category source IDs. ORDA
# will not publish an item without a category. 460202: Autonomous agents and multiagent systems;
# 461001: Digital curation and preservation; 460504: Data quality.
CATEGORIES = ["460202", "461001", "460504"]

# Figshare's item type for software.
DEFINED_TYPE = "software"

# Seconds to wait for one API call or one uploaded part.
TIMEOUT = 120


class OrdaError(Exception):
    """A call to the API failed; the message says which and why."""


class Client:
    """The few Figshare API calls this script needs, with the token in the header."""

    def __init__(self, api: str, token: str) -> None:
        self.api = api.rstrip("/")
        self.token = token

    def call(self, method: str, path: str, body: Any = None) -> Any:
        url = path if path.startswith(("https://", "http://")) else f"{self.api}{path}"
        data = None if body is None else json.dumps(body).encode()
        return self._send(method, url, data, "application/json")

    def put_bytes(self, url: str, data: bytes) -> None:
        self._send("PUT", url, data, "application/octet-stream")

    def _send(self, method: str, url: str, data: bytes | None, content_type: str) -> Any:
        request = urllib.request.Request(url, data=data, method=method)
        request.add_header("Authorization", f"token {self.token}")
        request.add_header("Content-Type", content_type)
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                text = response.read().decode()
        except urllib.error.HTTPError as error:
            detail = error.read().decode(errors="replace")
            raise OrdaError(f"{method} {url} returned {error.code}: {detail}") from error
        except urllib.error.URLError as error:
            raise OrdaError(f"{method} {url} failed: {error.reason}") from error
        return json.loads(text) if text else None


def read_citation() -> dict[str, Any]:
    with CITATION.open(encoding="utf-8") as stream:
        citation: dict[str, Any] = yaml.safe_load(stream)
    return citation


def components() -> dict[str, str]:
    """Each released package's version, by its path, from release-please's manifest."""
    versions: dict[str, str] = json.loads(MANIFEST.read_text(encoding="utf-8"))
    return versions


def authors(citation: dict[str, Any]) -> list[dict[str, str]]:
    result = []
    for person in citation["authors"]:
        if "name" in person:
            result.append({"name": person["name"]})
            continue
        author = {"first_name": person["given-names"], "last_name": person["family-names"]}
        if orcid := person.get("orcid"):
            author["orcid_id"] = orcid.removeprefix("https://orcid.org/")
        result.append(author)
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


def related_materials(citation: dict[str, Any], commit: str | None) -> list[dict[str, Any]]:
    code = citation["repository-code"].rstrip("/")
    materials: list[dict[str, Any]] = [
        {
            "identifier": f"{code}/tree/{commit}" if commit else code,
            "identifier_type": "URL",
            "relation": "IsSupplementTo",
            "title": "Source code on GitHub",
            "is_linkout": True,
        }
    ]
    for reference in citation.get("references", []):
        if doi := reference.get("doi"):
            materials.append(
                {
                    "identifier": doi,
                    "identifier_type": "DOI",
                    "relation": "References",
                    "title": reference["title"],
                    "is_linkout": False,
                }
            )
    return materials


def metadata(citation: dict[str, Any], commit: str | None, licence: int | str) -> dict[str, Any]:
    """The item's metadata, apart from its authors, which Figshare sets through their own call."""
    return {
        "title": citation["title"],
        "description": description(citation, commit),
        "defined_type": DEFINED_TYPE,
        "keywords": citation["keywords"],
        "categories_by_source_id": CATEGORIES,
        "license": licence,
        "related_materials": related_materials(citation, commit),
    }


def licence_id(client: Client, spdx: str) -> int:
    """ORDA numbers its licences; find the one named by CITATION.cff's SPDX identifier."""
    licences = client.call("GET", "/account/licenses")
    for licence in licences:
        if licence["name"] == spdx:
            value: int = licence["value"]
            return value
    names = ", ".join(licence["name"] for licence in licences)
    raise OrdaError(f"ORDA offers no licence named {spdx!r}; it offers: {names}")


def upload(client: Client, article: int, archive: Path) -> None:
    """Upload one file through Figshare's multi-part upload service."""
    content = archive.read_bytes()
    created = client.call(
        "POST",
        f"/account/articles/{article}/files",
        {"name": archive.name, "size": len(content), "md5": hashlib.md5(content).hexdigest()},
    )
    file = client.call("GET", created["location"])
    upload_url = file["upload_url"]
    for part in client.call("GET", upload_url)["parts"]:
        chunk = content[part["startOffset"] : part["endOffset"] + 1]
        client.put_bytes(f"{upload_url}/{part['partNo']}", chunk)
    client.call("POST", f"/account/articles/{article}/files/{file['id']}")


def create(client: Client, citation: dict[str, Any]) -> None:
    body = metadata(citation, None, licence_id(client, citation["license"]))
    location = client.call("POST", "/account/articles", body)["location"]
    article = client.call("GET", location)["id"]
    client.call("PUT", f"/account/articles/{article}/authors", {"authors": authors(citation)})
    doi = client.call("POST", f"/account/articles/{article}/reserve_doi")["doi"]
    report(
        f"Created private ORDA item {article} with reserved DOI {doi}.",
        f"Set the repository variable ORDA_ARTICLE_ID to {article} and add `doi: {doi}` to"
        " CITATION.cff. Nothing is public until the first release publishes it.",
    )


def release(
    client: Client, citation: dict[str, Any], article: int, archive: Path, commit: str
) -> None:
    body = metadata(citation, commit, licence_id(client, citation["license"]))
    client.call("PUT", f"/account/articles/{article}", body)
    client.call("PUT", f"/account/articles/{article}/authors", {"authors": authors(citation)})
    # A new version holds only this release's archive, not the previous one.
    for file in client.call("GET", f"/account/articles/{article}/files"):
        client.call("DELETE", f"/account/articles/{article}/files/{file['id']}")
    upload(client, article, archive)
    client.call("POST", f"/account/articles/{article}/publish")
    doi = client.call("GET", f"/account/articles/{article}").get("doi")
    versions = client.call("GET", f"/articles/{article}/versions")
    latest = max((version["version"] for version in versions), default=None)
    if doi and latest:
        report(
            f"Published version {latest} of ORDA item {article}: https://doi.org/{doi}.v{latest}"
        )
    else:
        # ORDA may hold a version for review before it appears in public.
        report(f"Submitted ORDA item {article} for publication; it is not yet public.")


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
    raise OrdaError(f"{name} is not set")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("create", help="make the private item and reserve its DOI (once)")
    publish = commands.add_parser("release", help="publish a new version of the item")
    publish.add_argument("--archive", type=Path, required=True, help="the file to deposit")
    publish.add_argument("--commit", default=os.environ.get("GITHUB_SHA", ""), help="its commit")
    publish.add_argument("--dry-run", action="store_true", help="print the metadata and stop")
    args = parser.parse_args(argv)

    citation = read_citation()
    try:
        if args.command == "release" and args.dry_run:
            body = metadata(citation, args.commit or None, citation["license"])
            body["authors"] = authors(citation)
            print(json.dumps(body, indent=2))
            return 0
        client = Client(os.environ.get("ORDA_API") or DEFAULT_API, environment("ORDA_TOKEN"))
        if args.command == "create":
            create(client, citation)
        else:
            if not args.archive.is_file():
                raise OrdaError(f"{args.archive} does not exist")
            article = int(environment("ORDA_ARTICLE_ID"))
            release(client, citation, article, args.archive, args.commit)
    except OrdaError as error:
        print(f"orda: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
