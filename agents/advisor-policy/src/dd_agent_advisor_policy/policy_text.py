"""A policy's own text, read from the page or PDF that publishes it.

FAIRsharing's records are curated summaries of policies, and say nothing of most of what a
researcher needs: which repository, by when, for how long the data may be withheld, under which
licence. The policy's own text does. Each matched record's `homepage`, and any `policy_url` the
researcher gives, is fetched here and turned into plain text, which `extract.py` then reads.

`PolicyText.document()` is what is hashed and shown as evidence, under `dd-json-document-v1`
(docs/specs/grounding.md): the address, the media type, the SHA-256 of the bytes fetched, the text
and whether it was cut short. Its label is `policy-text:live:<date>`. There is no pinned copy, so
the harness's source check reports it as unresolved, as it does every live route.

HTML is turned into text with the standard library's parser, leaving out scripts, styles and the
page's navigation, header and footer. A PDF is read by `pdf_text.py`. Anything else is not read.

Many funders publish a policy as a PDF behind a short landing page ("ESRC research data policy
(PDF)"). A page whose text is shorter than `LANDING_CHARS` that links to PDFs on its own site has
up to `MAX_LINKED` of them read too, each with its address and hash in the evidence, and their text
is added to the page's under a line naming each address.

This module does not use the Data Director contract. It is one of the importers of `httpx`
(docs/specs/dependencies.md).
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
from typing import Any, Protocol
from urllib.parse import urljoin, urlsplit

import httpx

from dd_agent_advisor_policy import pdf_text
from dd_agent_advisor_policy.ror import USER_AGENT
from dd_sdk.registry import RegistryUnavailable, SnapshotRef

LABEL = "policy-text"
TIMEOUT_S = 30.0
# The most fetched from one address, and the most text kept from it: enough for a long policy,
# not enough to swamp a model's context or the envelope.
MAX_BYTES = 10_000_000
MAX_CHARS = 60_000

# A page with less text than this is a landing page, whose PDFs on the same site are read too.
LANDING_CHARS = 3_000
MAX_LINKED = 2

HTML = ("text/html", "application/xhtml+xml")
PDF = "application/pdf"
TEXT = "text/plain"

# Elements whose text is not the policy's: code, styling, and the site's own furniture.
_SKIPPED = frozenset(
    {"script", "style", "noscript", "template", "svg", "nav", "header", "footer", "head"}
)
# Elements after which a line ends, so that headings and paragraphs stay apart.
_BLOCKS = frozenset(
    {
        "p", "div", "br", "li", "ul", "ol", "tr", "td", "th", "table", "section", "article",
        "main", "aside", "h1", "h2", "h3", "h4", "h5", "h6", "dt", "dd", "blockquote", "pre",
    }
)  # fmt: skip
_SPACES = re.compile(r"[ \t\f\v\u00a0]+")
_LINES = re.compile(r"\n\s*\n+")
_ANY_SPACE = re.compile(r"\s+")
_SAYS_PDF = re.compile(r"\bpdf\b", re.IGNORECASE)


class _Text(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skipping = 0
        # Each link outside the skipped elements: its address and its text.
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._anchor: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a" and not self.skipping:
            self._href = dict(attrs).get("href")
            self._anchor = []
        if tag in _SKIPPED:
            self.skipping += 1
        elif tag in _BLOCKS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._href:
            self.links.append((self._href, " ".join("".join(self._anchor).split())))
            self._href = None
        if tag in _SKIPPED:
            self.skipping = max(0, self.skipping - 1)
        elif tag in _BLOCKS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        # In HTML, a line break inside text is a space; lines end only between blocks (`pre` is
        # rare in a policy, and is read the same way).
        if not self.skipping:
            self.parts.append(_ANY_SPACE.sub(" ", data))
            if self._href is not None:
                self._anchor.append(data)


def tidy(text: str) -> str:
    """Runs of spaces made one, each line trimmed, and blank lines made one."""
    lines = (_SPACES.sub(" ", line).strip() for line in text.splitlines())
    return _LINES.sub("\n\n", "\n".join(lines)).strip()


def _parse(html: str) -> _Text:
    parser = _Text()
    parser.feed(html)
    parser.close()
    return parser


def html_text(html: str) -> str:
    """The readable text of an HTML page."""
    return tidy("".join(_parse(html).parts))


def _host(url: str) -> str:
    return (urlsplit(url).hostname or "").removeprefix("www.")


def linked_pdfs(html: str, base: str) -> list[str]:
    """The PDFs a page links to on its own site, in the order linked, each once: links whose
    address ends in `.pdf`, or whose text says PDF."""
    out: list[str] = []
    for href, anchor in _parse(html).links:
        url = urljoin(base, href.strip())
        path = urlsplit(url).path.casefold()
        if not (path.endswith(".pdf") or _SAYS_PDF.search(anchor)):
            continue
        if readable_url(url) and _host(url) == _host(base) and url not in out:
            out.append(url)
    return out


@dataclass(frozen=True)
class Linked:
    """A document a landing page links to, read with it."""

    url: str
    sha256: str


@dataclass(frozen=True)
class PolicyText:
    url: str
    media_type: str
    sha256: str
    text: str
    truncated: bool = False
    linked: tuple[Linked, ...] = ()

    def document(self) -> dict[str, Any]:
        """What is hashed and shown as evidence."""
        return {
            "url": self.url,
            "media_type": self.media_type,
            "sha256": self.sha256,
            "text": self.text,
            "truncated": self.truncated,
            "linked": [{"url": d.url, "sha256": d.sha256} for d in self.linked],
        }


class UnreadableError(Exception):
    """The address answered, but with nothing that could be read as a policy's text: an
    unsupported type, an empty page, or a PDF with no text. Not the same as unavailable."""


def readable_url(value: str | None) -> str | None:
    """`value` if it is an http(s) address, else None."""
    if not value:
        return None
    parts = urlsplit(value.strip())
    return value.strip() if parts.scheme in ("http", "https") and parts.netloc else None


class Pages(Protocol):
    """Where policy pages are fetched from: `PolicyPages`, or a fake in tests."""

    def snapshot_ref(self) -> SnapshotRef: ...

    def fetch(self, url: str) -> PolicyText: ...


class PolicyPages:
    """Fetches policy pages over the web. A transport failure or an error status raises
    `RegistryUnavailable`; an answer that cannot be read raises `UnreadableError`."""

    def __init__(self, client: httpx.Client | None = None, now: datetime | None = None) -> None:
        self._client = client
        self._now = now

    def _http(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                timeout=TIMEOUT_S, headers={"User-Agent": USER_AGENT}, follow_redirects=True
            )
        return self._client

    def snapshot_ref(self) -> SnapshotRef:
        now = self._now or datetime.now(UTC)
        return SnapshotRef(
            label=f"{LABEL}:live:{now.date().isoformat()}",
            fetched_at=now.isoformat(timespec="seconds"),
        )

    def _get(self, url: str) -> tuple[bytes, str, str]:
        """The bytes at `url`, its media type and its encoding."""
        try:
            with self._http().stream("GET", url) as resp:
                if resp.status_code != 200:
                    raise RegistryUnavailable(f"{url}: HTTP {resp.status_code}")
                media_type = resp.headers.get("content-type", "").split(";")[0].strip().lower()
                body = bytearray()
                for chunk in resp.iter_bytes():
                    body += chunk
                    if len(body) > MAX_BYTES:
                        raise UnreadableError(f"{url}: larger than {MAX_BYTES} bytes")
                encoding = resp.encoding or "utf-8"
        except httpx.HTTPError as exc:
            raise RegistryUnavailable(f"{url}: {exc}") from None
        return bytes(body), media_type, encoding

    def fetch(self, url: str) -> PolicyText:
        data, media_type, encoding = self._get(url)
        truncated = False
        linked: list[Linked] = []
        if media_type == PDF or (not media_type and data.startswith(b"%PDF")):
            text, truncated = _pdf(url, data)
            media_type = PDF
        elif media_type in HTML:
            html = data.decode(encoding, errors="replace")
            text = html_text(html)
            if len(text) < LANDING_CHARS:
                for pdf_url in linked_pdfs(html, url)[:MAX_LINKED]:
                    try:
                        pdf, _, _ = self._get(pdf_url)
                        more, cut = _pdf(pdf_url, pdf)
                    except RegistryUnavailable, UnreadableError:
                        continue  # the landing page is still read
                    linked.append(Linked(pdf_url, hashlib.sha256(pdf).hexdigest()))
                    text += f"\n\n[From {pdf_url}]\n\n{more}"
                    truncated = truncated or cut
        elif media_type == TEXT:
            text = tidy(data.decode(encoding, errors="replace"))
        else:
            raise UnreadableError(f"{url}: {media_type or 'no media type'} is not read")
        if not text:
            raise UnreadableError(f"{url}: no text")
        if len(text) > MAX_CHARS:
            text, truncated = text[:MAX_CHARS], True
        return PolicyText(
            url=url,
            media_type=media_type,
            sha256=hashlib.sha256(data).hexdigest(),
            text=text,
            truncated=truncated,
            linked=tuple(linked),
        )


def _pdf(url: str, data: bytes) -> tuple[str, bool]:
    read = pdf_text.text(data)
    if read is None:
        raise UnreadableError(f"{url}: a PDF with no text that can be read")
    return tidy(read[0]), read[1]
