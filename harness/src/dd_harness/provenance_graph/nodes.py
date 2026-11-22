"""The graph a provenance graph is built in, and the IRIs and nodes every part of it shares
(docs/specs/provenance.md, Identifiers).

Every node is a top-level node with an IRI, a qualified one included, so the graph has no blank
nodes and serialises to the same bytes whatever order it was built in.
"""

from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Iterable, Mapping
from typing import Any

from dd_harness.provenance import AGENT_BASE

CONTEXT = {
    "prov": "http://www.w3.org/ns/prov#",
    "schema": "http://schema.org/",
    "dd": "https://w3id.org/data-director/",
    "xsd": "http://www.w3.org/2001/XMLSchema#",
}
# Where a model and the harness are named, beside the agents (TODO(#3): the w3id namespace is not
# yet registered).
MODEL_BASE = "https://w3id.org/data-director/models/"
HARNESS = "https://w3id.org/data-director/harness"
_HEX64 = frozenset("0123456789abcdef")


def uuid_iri(identifier: str) -> str:
    """The IRI of something the record names by a UUID: a project, an event, a run."""
    return f"urn:uuid:{identifier}"


def version_id(document_id: str, version: int) -> str:
    return f"urn:uuid:{document_id}#v{version}"


def agent_iri(agent_id: str) -> str:
    return AGENT_BASE + agent_id


def model_iri(provider: str, model_id: str) -> str:
    return f"{MODEL_BASE}{provider or 'unknown'}/{model_id}"


def is_digest(value: object) -> bool:
    """Whether `value` is a SHA-256 hex digest."""
    return isinstance(value, str) and len(value) == 64 and set(value) <= _HEX64


def ni(digest: str) -> str:
    """The RFC 6920 `ni` URI of a SHA-256 hex digest."""
    raw = bytes.fromhex(digest)
    return "ni:///sha-256;" + base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def digest_of(value: Any) -> str:
    """The SHA-256 of `value`: of its UTF-8 bytes for a string, else of its canonical JSON."""
    if isinstance(value, str):
        data = value.encode("utf-8")
    else:
        data = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(data).hexdigest()


def ref(iri: str) -> dict[str, str]:
    return {"@id": iri}


def dt(value: str) -> dict[str, str]:
    return {"@value": value, "@type": "xsd:dateTime"}


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


class Graph:
    """Nodes by IRI. `put` merges a node into the one with its IRI: each property holds the
    union of the values given for it, so the order nodes are put in does not matter."""

    def __init__(self) -> None:
        self.nodes: dict[str, dict[str, list[Any]]] = {}

    def put(self, iri: str, *types: str, **properties: Any) -> str:
        """Merge into the node `iri` its `types` and `properties`, whose names are prefixed terms
        written with `__` for `:` (`prov__used`). A value of None is left out; a list or tuple
        gives several values. Returns `iri`."""
        node = self.nodes.setdefault(iri, {})
        if types:
            _add(node, "@type", types)
        for name, value in properties.items():
            if value is None:
                continue
            values = value if isinstance(value, list | tuple) else [value]
            _add(node, name.replace("__", ":"), values)
        return iri

    def link(self, subject: str, term: str, *objects: str) -> None:
        """`subject` `term` each of `objects`, by IRI."""
        _add(self.nodes.setdefault(subject, {}), term, [ref(o) for o in objects])

    def content(self, digest: str, *types: str, **properties: Any) -> str:
        """The entity named by the SHA-256 `digest` of its content (invariant 5)."""
        return self.put(ni(digest), "prov:Entity", *types, schema__sha256=digest, **properties)

    def principal(self, principal: Mapping[str, Any]) -> str:
        """A principal, by what identifies them and nothing else (invariants 4 and 6): a person
        is a `prov:Person`; an accountable role a `prov:Agent` typed `dd:AccountableRole`."""
        iri = str(principal["principal_id"])
        if principal.get("principal_kind") == "accountable_role":
            types: tuple[str, ...] = ("prov:Agent", "dd:AccountableRole")
        else:
            types = ("prov:Person", "schema:Person")
        return self.put(
            iri,
            *types,
            schema__name=principal.get("name"),
            dd__principalKind=principal.get("principal_kind", "person"),
            dd__assurance=principal.get("assurance", "asserted"),
            dd__vouchedBy=ref(principal["vouched_by"]) if principal.get("vouched_by") else None,
        )

    def acting_for(self, agent: str, activity: str, principal: Mapping[str, Any] | str) -> None:
        """`agent` acted for `principal` in `activity`, and in no other (invariant 4)."""
        person = principal if isinstance(principal, str) else self.principal(principal)
        delegation = self.put(
            f"{activity}#delegation",
            "prov:Delegation",
            prov__agent=ref(person),
            prov__hadActivity=ref(activity),
        )
        self.link(agent, "prov:qualifiedDelegation", delegation)

    def harness(self) -> str:
        return self.put(
            HARNESS,
            "prov:SoftwareAgent",
            "schema:SoftwareApplication",
            schema__name="Data Director harness",
        )

    def jsonld(self, keep: Iterable[str] | None = None) -> dict[str, Any]:
        """The graph in JSON-LD, its nodes sorted by IRI and each value list sorted, so the same
        graph gives the same document. With `keep`, only those nodes, and of their references
        to other nodes of the graph only those to nodes kept."""
        kept = set(self.nodes if keep is None else keep) & set(self.nodes)
        out = []
        for iri in sorted(kept):
            node: dict[str, Any] = {"@id": iri}
            for term, values in self.nodes[iri].items():
                values = [v for v in values if not _dangling(v, kept, self.nodes)]
                if values:
                    ordered = sorted(values, key=canonical)
                    node[term] = ordered[0] if len(ordered) == 1 else ordered
            out.append(node)
        return {"@context": CONTEXT, "@graph": out}


def _add(node: dict[str, list[Any]], term: str, values: Iterable[Any]) -> None:
    held = node.setdefault(term, [])
    seen = {canonical(v) for v in held}
    for value in values:
        if (key := canonical(value)) not in seen:
            held.append(value)
            seen.add(key)


def _dangling(value: Any, kept: set[str], nodes: Mapping[str, Any]) -> bool:
    """A reference to a node of the graph that is not kept."""
    return (
        isinstance(value, dict)
        and set(value) == {"@id"}
        and value["@id"] in nodes
        and value["@id"] not in kept
    )
