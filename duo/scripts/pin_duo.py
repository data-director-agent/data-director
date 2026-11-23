# /// script
# requires-python = ">=3.14"
# dependencies = []
# ///
"""Pin a release of the GA4GH Data Use Ontology (DUO) as the terms `dd_duo` describes.

Reads `duo.owl` (RDF/XML) of one tagged DUO release and writes one JSON record per current data
use permission or modifier, with a manifest, to `src/dd_duo/data/`:

    curl -sfLO https://raw.githubusercontent.com/EBISPOT/DUO/v2021-02-23/duo.owl
    uv run --no-project --python 3.14 duo/scripts/pin_duo.py duo.owl --version 2021-02-23

Each record keeps the term's identifier, shorthand, label, definition, whether it is a permission
or a modifier, and its broader term other than the two roots. The two root classes, obsolete terms and the research-type classes
that are neither are left out. The output is reproducible: the same input gives the same bytes.

DUO is under CC BY 4.0 (`src/dd_duo/data/LICENCE.md`).
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from xml.etree import ElementTree

OUT = Path(__file__).resolve().parents[1] / "src" / "dd_duo" / "data"
SOURCE = "https://github.com/EBISPOT/DUO/blob/v{version}/duo.owl"
OBO = "http://purl.obolibrary.org/obo/"
RDF = "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}"
RDFS = "{http://www.w3.org/2000/01/rdf-schema#}"
OWL = "{http://www.w3.org/2002/07/owl#}"
OBO_IN_OWL = "{http://www.geneontology.org/formats/oboInOwl#}"
DEFINITION = "{http://purl.obolibrary.org/obo/}IAO_0000115"
# The two roots under which every term DUO applies to a dataset sits.
ROOTS = {"DUO:0000001": "permission", "DUO:0000017": "modifier"}


def _curie(iri: str) -> str:
    """`http://purl.obolibrary.org/obo/DUO_0000021` as `DUO:0000021`; other IRIs as they are."""
    local = iri.removeprefix(OBO)
    return local.replace("_", ":", 1) if local != iri else iri


def _classes(root: ElementTree.Element) -> dict[str, ElementTree.Element]:
    """Each DUO class, by its identifier as the class states it (`oboInOwl:id`)."""
    found = {}
    for element in root.iter(f"{OWL}Class"):
        term_id = element.findtext(f"{OBO_IN_OWL}id")
        if term_id and term_id.startswith("DUO:"):
            found[term_id.strip()] = element
    return found


def _parents(element: ElementTree.Element) -> list[str]:
    """The named classes this class is a subclass of (restrictions are skipped)."""
    return [
        _curie(resource)
        for sub in element.findall(f"{RDFS}subClassOf")
        if (resource := sub.get(f"{RDF}resource"))
    ]


def _obsolete(element: ElementTree.Element) -> bool:
    label = (element.findtext(f"{RDFS}label") or "").lower()
    return (
        (element.findtext(f"{OWL}deprecated") or "").strip() == "true"
        or any(p.endswith("ObsoleteClass") for p in _parents(element))
        or label.startswith("obsolete")
    )


def _kind(term_id: str, classes: dict[str, ElementTree.Element]) -> str | None:
    """`permission` or `modifier` for a term under one of the roots, else None."""
    seen: set[str] = set()
    todo = [term_id]
    while todo:
        current = todo.pop()
        if current in ROOTS and current != term_id:
            return ROOTS[current]
        if current in seen or current not in classes:
            continue
        seen.add(current)
        todo.extend(_parents(classes[current]))
    return None


def records(owl: bytes) -> list[dict[str, object]]:
    """The current permissions and modifiers of one DUO release, in identifier order."""
    classes = _classes(ElementTree.fromstring(owl))
    out: list[dict[str, object]] = []
    for term_id, element in sorted(classes.items()):
        kind = _kind(term_id, classes)
        if kind is None or _obsolete(element):
            continue
        parent = next(
            (p for p in _parents(element) if p.startswith("DUO:") and p not in ROOTS), None
        )
        out.append(
            {
                "id": term_id,
                "shorthand": (element.findtext(f"{OBO_IN_OWL}shorthand") or "").strip() or None,
                "label": (element.findtext(f"{RDFS}label") or "").strip(),
                "definition": (element.findtext(DEFINITION) or "").strip(),
                "kind": kind,
                "parent": parent,
                "url": OBO + term_id.replace(":", "_"),
            }
        )
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("owl", type=Path, help="duo.owl of one release (RDF/XML)")
    parser.add_argument("--version", required=True, help="the release tag's date, e.g. 2021-02-23")
    args = parser.parse_args()

    raw = args.owl.read_bytes()
    terms = records(raw)
    data = "".join(json.dumps(t, ensure_ascii=False, sort_keys=True) + "\n" for t in terms)
    encoded = data.encode("utf-8")
    name = f"duo-{args.version}.jsonl"
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_bytes(encoded)
    manifest = {
        "duo_version": args.version,
        "source": SOURCE.format(version=args.version),
        "derived_from": {"file": args.owl.name, "sha256": hashlib.sha256(raw).hexdigest()},
        "terms": {
            "file": name,
            "sha256": hashlib.sha256(encoded).hexdigest(),
            "count": len(terms),
        },
        "licence": "CC-BY-4.0",
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(terms)} terms to {OUT / name}")


if __name__ == "__main__":
    main()
