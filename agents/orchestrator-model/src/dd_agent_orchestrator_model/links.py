"""Links in a reply: the web addresses an agent's sources have, and the check that a reply links
only to an address it was given.

A researcher who wants to check a citation needs the address of the source, so each delegated
result handed to the model lists its sources' web addresses (`cited_sources`), and the prompt asks
the model to link a source by one of them. The model writes the reply, so a link in it is a claim
about where a source is, and nothing else checks it: an address the model made up would read as a
citation. `checked` therefore keeps a link only when its address appears in what the model was
shown (an agent's result, the researcher's words or an earlier reply) and shows any other as plain
text, never as a link. Only `http` and `https` addresses are judged; the app opens them in a new
tab.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from typing import Any, Final

from dd_sdk.contract.models import Envelope

_ADDRESS: Final = r"https?://[^\s<>\"')\]]+"
_FOUND: Final = re.compile(_ADDRESS)
# What can be a link in Markdown, in the order they must be tried: code, which is never one, then
# `[label](address)`, then `<address>`, then an address standing alone (the app autolinks these).
_LINKED: Final = re.compile(
    r"(?P<code>```[\s\S]*?```|`[^`\n]*`)"
    r"|\[(?P<label>[^\]]*)\]\((?P<dest>https?://[^)\s]+)(?:\s+\"[^\"]*\")?\)"
    rf"|<(?P<angle>{_ADDRESS})>"
    rf"|(?P<bare>{_ADDRESS})"
)
_TRAILING: Final = ".,;:!?"


def _same(address: str) -> str:
    """An address as compared: without punctuation that ended a sentence or a final slash."""
    return address.rstrip(_TRAILING).rstrip("/")


def _titled(content: dict[str, Any] | None) -> str | None:
    for key in ("title", "name"):
        value = (content or {}).get(key)
        if isinstance(value, str) and value:
            return value
    return None


def cited_sources(envelope: Envelope) -> list[dict[str, str]]:
    """The web addresses of the sources `envelope` cites, each with its id, and its title when
    the cited record has one, for the model to link by. Sources without a web address, such as a
    record read from a local snapshot, are left out."""
    found: list[dict[str, str]] = []
    for item in envelope.evidence:
        if not item.source_uri or not _FOUND.fullmatch(item.source_uri):
            continue
        entry = {"source_id": item.source_id, "url": item.source_uri}
        if (title := _titled(item.content)) is not None:
            entry["title"] = title
        found.append(entry)
    return found


def addresses_in(text: str) -> set[str]:
    """Every web address written in `text`."""
    return {_same(m) for m in _FOUND.findall(text)}


def shown_addresses(envelopes: Iterable[Envelope], *texts: str) -> set[str]:
    """The web addresses the model was shown: those in each result's payload and sources, and in
    `texts`, such as the researcher's message and the conversation so far."""
    shown: set[str] = set()
    for envelope in envelopes:
        shown |= {_same(s["url"]) for s in cited_sources(envelope)}
        if envelope.payload is not None:
            shown |= addresses_in(json.dumps(envelope.payload.model_dump(mode="json"), default=str))
    for text in texts:
        shown |= addresses_in(text)
    return shown


def checked(text: str, shown: set[str]) -> str:
    """`text` with each link to an address not in `shown` made plain: a `[label](address)` link
    keeps its label, and an address standing alone or in angle brackets becomes inline code."""

    def plain(address: str) -> str:
        # Punctuation that ended a sentence stays outside the code.
        stripped = address.rstrip(_TRAILING)
        return f"`{stripped}`{address[len(stripped) :]}"

    def settle(found: re.Match[str]) -> str:
        if found["code"] is not None:
            return str(found["code"])
        if found["dest"] is not None:
            if _same(found["dest"]) in shown:
                return str(found[0])
            return str(found["label"]) or plain(found["dest"])
        address = found["angle"] or found["bare"]
        return str(found[0]) if _same(address) in shown else plain(address)

    return _LINKED.sub(settle, text)
