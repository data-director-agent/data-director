"""The documents a researcher attached to the project, read as a policy's own text (#1326).

Most researchers hold their institution's policy, or their award letter, as a document rather
than an address. In a project the conductor gives each attached document with its text
(`GivenProjectDocuments`, docs/specs/projects.md), and here each becomes a `PolicyText` that
`reading.py` reads as it reads a fetched page: the same extractor, the same check that every quote
is in the text, and the document cited as evidence of its own, under its SHA-256.

A document is read for the actor it names: each actor whose name appears in its file name or its
text. Where it names none and the context has one actor, it is read for that actor; otherwise it
is not guessed, and the statement says that it was not read and why. Whether the text reaches a
hosted model at all is the deployment's choice (`hosted_models`, docs/specs/policy-and-identity.md):
where the profile keeps documentation from the agent's model, the conductor leaves the documents
out and there is nothing here to read.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from dd_agent_advisor_policy.classes import Actor
from dd_agent_advisor_policy.policy_text import MAX_CHARS, PolicyText
from dd_sdk.contract.facts import ProjectDocument

# The source id of an attached document, by its SHA-256: it has no address of its own.
SOURCE_PREFIX = "attached:"


def as_text(document: ProjectDocument) -> PolicyText:
    """The document as a policy's text, cut to what a fetched page keeps."""
    text = document.documentation_text
    return PolicyText(
        url=f"{SOURCE_PREFIX}{document.documentation_digest}",
        media_type=document.documentation_media_type,
        sha256=document.documentation_digest,
        text=text[:MAX_CHARS],
        truncated=len(text) > MAX_CHARS,
        name=document.documentation_name,
    )


@dataclass
class Targets:
    """Each attached document paired with the actors it is read for, and the names of those
    read for none."""

    pairs: list[tuple[Actor, PolicyText]] = field(default_factory=list)
    unmatched: list[str] = field(default_factory=list)


def targets(documents: list[ProjectDocument], actors: list[Actor]) -> Targets:
    """Which actor each document is read for: those it names, or the only one there is."""
    out = Targets()
    for document in documents:
        named = _named(document, actors)
        if not named and len(actors) == 1:
            named = list(actors)
        if not named:
            out.unmatched.append(document.documentation_name)
            continue
        text = as_text(document)
        out.pairs += [(actor, text) for actor in named]
    return out


def _named(document: ProjectDocument, actors: list[Actor]) -> list[Actor]:
    haystack = f"{document.documentation_name}\n{document.documentation_text}".casefold()
    return [actor for actor in actors if actor.name.strip().casefold() in haystack]
