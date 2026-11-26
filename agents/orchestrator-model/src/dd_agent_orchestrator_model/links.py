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

import re
from collections.abc import Iterable, Iterator
from typing import Any, Final

from dd_sdk.contract.models import Envelope

_SCHEME: Final = r"(?i:https?)://"
# An address in prose: it ends at white space, a quote, an angle bracket or an unbalanced bracket,
# and may hold one level of balanced parentheses, as a Wikipedia address does.
_CHARS: Final = r"[^\s<>\"')\]()]"
_ADDRESS: Final = rf"{_SCHEME}(?:{_CHARS}|\({_CHARS}*\))+"
_FOUND: Final = re.compile(_ADDRESS)
# A source's address as listed for the model: anything the Markdown link below can carry.
_LISTABLE: Final = re.compile(rf"{_SCHEME}[^\s<>\x00-\x1f]+")
_DEST: Final = r"(?:[^()\s]|\([^()\s]*\))+"
_TITLE: Final = r"""(?:\s+(?:"[^"]*"|'[^']*'|\([^)]*\)))?"""
# What can be a link in Markdown, in the order they must be tried: code, which is never one, then
# a reference definition, `[label](address)` (an image too), `<address>`, an address standing alone
# and a `www.` address (the app autolinks both of the last two).
_LINKED: Final = re.compile(
    r"(?P<code>```[\s\S]*?```|`[^`\n]*`)"
    rf"|(?P<def>^ {{0,3}}\[(?P<ref>[^\]\n]+)\]:[ \t]*<?(?P<rdest>{_ADDRESS})>?[^\n]*(?:\n|$))"
    rf"|(?P<bang>!)?\[(?P<label>[^\]]*)\]\(\s*(?:<(?P<adest>{_SCHEME}[^>\s]+)>|(?P<dest>{_SCHEME}{_DEST}))"
    rf"{_TITLE}\s*\)"
    rf"|<(?P<angle>{_ADDRESS})>"
    rf"|(?P<bare>{_ADDRESS})"
    r"|(?P<www>(?<![\w/.@:-])www\.[^\s<>\"')\]]+)",
    re.MULTILINE,
)
_REFERENCE: Final = re.compile(r"\[(?P<label>[^\]]*)\]\[(?P<ref>[^\]]+)\]")
_TRAILING: Final = ".,;:!?"


def _same(address: str) -> str:
    """An address as compared: without punctuation that ended a sentence or a final slash, and
    with its scheme in lower case."""
    kept = address.rstrip(_TRAILING).rstrip("/")
    scheme, found, rest = kept.partition("://")
    return f"{scheme.lower()}{found}{rest}"


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
        if not item.source_uri or not _LISTABLE.fullmatch(item.source_uri):
            continue
        entry = {"source_id": item.source_id, "url": item.source_uri}
        if (title := _titled(item.content)) is not None:
            entry["title"] = title
        found.append(entry)
    return found


def addresses_in(text: str) -> set[str]:
    """Every web address written in `text`."""
    return {_same(m) for m in _FOUND.findall(text)}


def _strings(value: object) -> Iterator[str]:
    """Every string in a JSON value, as the model reads it, without JSON's escapes."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)


def shown_addresses(envelopes: Iterable[Envelope], *texts: str) -> set[str]:
    """The web addresses the model was shown: those in each result's payload and sources, and in
    `texts`, such as the researcher's message and the conversation so far."""
    shown: set[str] = set()
    for envelope in envelopes:
        shown |= {_same(s["url"]) for s in cited_sources(envelope)}
        if envelope.payload is not None:
            for text in _strings(envelope.payload.model_dump(mode="json")):
                shown |= addresses_in(text)
    for text in texts:
        shown |= addresses_in(text)
    return shown


def _plain(address: str) -> str:
    # Punctuation that ended a sentence stays outside the code.
    stripped = address.rstrip(_TRAILING)
    return f"`{stripped}`{address[len(stripped) :]}"


def _dropped_definition(found: re.Match[str], shown: set[str], dropped: set[str]) -> str:
    if _same(found["rdest"]) in shown:
        return str(found[0])
    dropped.add(found["ref"].lower())
    return ""


def _link(found: re.Match[str], dest: str, shown: set[str], dropped: set[str]) -> str:
    if _same(dest) in shown:
        return str(found[0])
    return _check(found["label"], shown, dropped) or _plain(dest)


def _settle(found: re.Match[str], shown: set[str], dropped: set[str]) -> str:
    if found["code"] is not None:
        return str(found["code"])
    if found["def"] is not None:
        return _dropped_definition(found, shown, dropped)
    if (dest := found["dest"] or found["adest"]) is not None:
        return _link(found, dest, shown, dropped)
    if (www := found["www"]) is not None:
        seen = _same(f"http://{www}") in shown or _same(f"https://{www}") in shown
        return www if seen else _plain(www)
    address = found["angle"] or found["bare"]
    return str(found[0]) if _same(address) in shown else _plain(address)


def _check(text: str, shown: set[str], dropped: set[str]) -> str:
    return _LINKED.sub(lambda found: _settle(found, shown, dropped), text)


def checked(text: str, shown: set[str]) -> str:
    """`text` with each link to an address not in `shown` made plain: a `[label](address)` link
    keeps its label (an image its description), a reference-style link keeps its label and loses
    its definition, and an address standing alone, in angle brackets or after `www.` becomes
    inline code. A label that is itself such an address is made plain in the same way."""
    dropped: set[str] = set()
    result = _check(text, shown, dropped)
    if not dropped:
        return result

    def unreferenced(found: re.Match[str]) -> str:
        if found["ref"].lower() not in dropped:
            return str(found[0])
        return str(found["label"] or found["ref"])

    return _REFERENCE.sub(unreferenced, result)
