"""Look for possible personal data and secrets in a document before it is attached (#473).

A document a researcher attaches is kept as text, and a drafter may be given it
(docs/specs/projects.md). Before it is accepted, its text is checked here, on the server that
already holds it, for what should not be in it:

- possible personal data, by the inventory command's own detector (`dd_inventory.personal`):
  Presidio's pattern recognisers, with no language model, so names and places are not found;
- secrets, by detect-secrets' named plugins (keys and tokens of known services, private keys,
  passwords given to a keyword). Its entropy plugins are left out: they flag ordinary words.

A finding is a kind and how sure the check is, never a value, a line or an offset, so what
is found is never repeated in a response or a log. A finding is a prompt for a person, who may
attach the document anyway (docs/specs/personal-data.md); nothing here changes the text.
"""

from __future__ import annotations

import logging
import threading
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from importlib.metadata import version

from dd_app.turn_body import AttachedDocument
from dd_harness.projects import check_documentation
from dd_inventory.personal import confidence_band, default_detector

log = logging.getLogger(__name__)

SECRET = "secret"
# detect-secrets' plugins that judge a string by how random it looks: in prose they flag words.
ENTROPY_TYPES = frozenset({"Base64 High Entropy String", "Hex High Entropy String"})
# detect-secrets' settings are global to the process, so one scan runs at a time.
_SECRETS_LOCK = threading.Lock()


@dataclass(frozen=True)
class TextFinding:
    """What may be in a document: a kind of personal data, or `secret` with the type of secret
    as its detail; how many places, as a band; and how sure the check is."""

    kind: str
    detail: str | None
    places: str
    confidence: str

    def as_json(self) -> dict[str, str]:
        found = {"kind": self.kind, "places": self.places, "confidence": self.confidence}
        return {**found, "detail": self.detail} if self.detail else found


def places_band(count: int) -> str:
    """How many places, as a band, so that a finding cannot be turned into a count."""
    if count == 1:
        return "1"
    return "2 to 4" if count < 5 else "5 or more"


def checked_with() -> str:
    """What the check ran, to say alongside its findings."""
    return (
        f"{default_detector().description}; detect-secrets {version('detect-secrets')}, named "
        "plugins only"
    )


def _personal_data(text: str) -> list[TextFinding]:
    counts: dict[str, int] = defaultdict(int)
    best: dict[str, float] = {}
    for hit in default_detector().analyse(text, ()):
        counts[hit.kind] += 1
        best[hit.kind] = max(hit.score, best.get(hit.kind, 0.0))
    return [
        TextFinding(kind, None, places_band(counts[kind]), confidence_band(best[kind]))
        for kind in sorted(counts)
    ]


def _secrets(text: str) -> list[TextFinding]:
    from detect_secrets.core.plugins.util import get_mapping_from_secret_type_to_class
    from detect_secrets.core.scan import scan_line
    from detect_secrets.settings import transient_settings

    named: dict[str, type] = get_mapping_from_secret_type_to_class()
    plugins = [{"name": cls.__name__} for kind, cls in named.items() if kind not in ENTROPY_TYPES]
    counts: dict[str, int] = defaultdict(int)
    with _SECRETS_LOCK, transient_settings({"plugins_used": plugins}):
        for line in text.splitlines():
            for secret in {s.type for s in scan_line(line)}:
                counts[secret] += 1
    return [TextFinding(SECRET, t, places_band(n), "high") for t, n in sorted(counts.items())]


def screen(text: str) -> list[TextFinding]:
    """The possible personal data and secrets in `text`, by kind; empty when none was found,
    which does not mean there is none."""
    return _personal_data(text) + _secrets(text)


def kinds(findings: list[TextFinding]) -> list[str]:
    """The kinds a researcher confirms: a secret's type stands for itself."""
    return sorted({f.detail if f.kind == SECRET and f.detail else f.kind for f in findings})


class DocumentationHeldError(ValueError):
    """A document in which possible personal data or secrets were found, sent without the
    researcher confirming what was found. Nothing was added or run (docs/specs/app.md)."""

    def __init__(self, unconfirmed: list[str]) -> None:
        self.kinds = unconfirmed
        super().__init__(
            "This document may hold "
            + ", ".join(unconfirmed)
            + ". Check it, and attach it again confirming what was found, or remove them first."
        )


def hold(name: str, text: str, confirmed: Iterable[str]) -> list[TextFinding]:
    """The findings in a document the researcher sends, once they have confirmed every kind;
    raises `DocumentationHeldError` naming those they have not. Logs the document's name and
    the kinds, never a value."""
    findings = screen(text)
    unconfirmed = sorted(set(kinds(findings)) - set(confirmed))
    if unconfirmed:
        log.info("data-director: document %r held for confirmation: %s", name, unconfirmed)
        raise DocumentationHeldError(unconfirmed)
    if findings:
        log.info("data-director: document %r attached as confirmed: %s", name, kinds(findings))
    return findings


def accept(document: AttachedDocument) -> list[TextFinding]:
    """A document a turn attaches, checked as the project would check it and then held unless
    every kind found is confirmed (`hold`). Raises `ProjectError` or `DocumentationHeldError`."""
    check_documentation(document.name, document.media_type, document.text)
    return hold(document.name, document.text, document.confirmed)
