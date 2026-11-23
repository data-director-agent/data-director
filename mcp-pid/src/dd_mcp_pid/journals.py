"""The `journals` server: journals by ISSN or title, from the `dd-journals` registry.

The registry is a local copy built from a pinned OpenAlex snapshot (CC0) by `dd-journals fetch`,
or `dd-sources prepare` in the Data Director, so a look-up sends nothing anywhere. It is opened on
the first call, not at start-up, so the server lists its tools even before the registry is built;
until then each call is an error that says how to build it.

Each record is identified by its linking ISSN (`issn_l`) and links to the journal's record in the
ISSN Portal, the ISSN International Centre's register. It holds no integer: OpenAlex's count of
works orders the search but is left out of the record.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mcp_types import CallToolResult, Tool

from dd_journals import Journal, PinError, Registry, normal_issn
from dd_mcp_pid.tools import Registry as ToolRegistry
from dd_mcp_pid.tools import found, records_schema, string_input, text

SEARCH_LIMIT = 10
_TEXT = {"type": "string"}
_OPTIONAL_TEXT = {"type": ["string", "null"]}
_TEXTS = {"type": "array", "items": _TEXT}
_FLAG = {"type": "boolean"}

JOURNAL = {
    "type": "object",
    "properties": {
        "issn_l": _TEXT,
        "issns": _TEXTS,
        "title": _TEXT,
        "alternate_titles": _TEXTS,
        "abbreviated_title": _OPTIONAL_TEXT,
        "publisher": _OPTIONAL_TEXT,
        "country": _OPTIONAL_TEXT,
        "homepage": _OPTIONAL_TEXT,
        "is_in_doaj": _FLAG,
        "is_oa": _FLAG,
        "openalex_id": _TEXT,
        "portal_url": _TEXT,
    },
    "required": [
        "issn_l",
        "issns",
        "title",
        "alternate_titles",
        "abbreviated_title",
        "publisher",
        "country",
        "homepage",
        "is_in_doaj",
        "is_oa",
        "openalex_id",
        "portal_url",
    ],
    "additionalProperties": False,
}

GET_JOURNAL = Tool(
    name="get_journal",
    description=(
        "A journal by any of its ISSNs (print, online or linking): its linking ISSN (ISSN-L), "
        "every ISSN, title, alternate and abbreviated titles, publisher, country, homepage, "
        "whether it is in DOAJ and open access, and its ISSN Portal record. From a pinned "
        "OpenAlex snapshot. No records if the snapshot has no journal with that ISSN."
    ),
    input_schema=string_input("issn", "An ISSN, with or without its hyphen (NNNN-NNNC)."),
    output_schema=records_schema(JOURNAL),
)

SEARCH_JOURNALS = Tool(
    name="search_journals",
    description=(
        f"Up to {SEARCH_LIMIT} journals for a title, part of one, or an ISSN, likeliest first: "
        "the journal with that ISSN; then titles that are the same, ignoring case, accents, "
        "punctuation, '&' for 'and' and a leading 'The'; then titles that start with the text; "
        "then titles with a word starting with each word given. Within each, journals with more "
        "works come first. More than one means the title is ambiguous: ask which, by its ISSN."
    ),
    input_schema=string_input("text", "A journal's title, the start of it, or an ISSN."),
    output_schema=records_schema(JOURNAL, at_most_one=False),
)


def document(journal: Journal) -> dict[str, Any]:
    """The journal as a record: what `dd-journals` keeps, without its count of works."""
    record = {k: v for k, v in journal.as_dict().items() if k != "works_count"}
    record["portal_url"] = journal.portal_url
    return record


@dataclass
class JournalSource:
    """The registry at `path`, opened on the first look-up and then kept."""

    path: Path
    _registry: Registry | None = field(default=None, init=False, repr=False)

    def registry(self) -> Registry:
        if self._registry is None:
            self._registry = Registry(self.path)
        return self._registry


def _summary(journal: Journal) -> str:
    by = f", {journal.publisher}" if journal.publisher else ""
    return f"{journal.title} (ISSN-L {journal.issn_l}{by})"


def journal_registry(source: JournalSource) -> ToolRegistry:
    """The `journals` server."""

    def opened() -> Registry | CallToolResult:
        try:
            return source.registry()
        except PinError as exc:
            message = f"The journal registry cannot be read: {exc}. In the Data Director, run "
            return text(message + "`uv run dd-sources prepare`.", error=True)

    def get_journal(arguments: dict[str, Any]) -> CallToolResult:
        issn = normal_issn(str(arguments.get("issn") or ""))
        if issn is None:
            return text("Not an ISSN: give NNNN-NNNC, with or without the hyphen.", error=True)
        registry = opened()
        if isinstance(registry, CallToolResult):
            return registry
        journal = registry.get(issn)
        where = registry.label or "the journal registry"
        if journal is None:
            return found([], f"{where} has no journal with ISSN {issn}.")
        return found([document(journal)], f"{where}: {_summary(journal)}.")

    def search_journals(arguments: dict[str, Any]) -> CallToolResult:
        words = " ".join(str(arguments.get("text") or "").split())
        if not words:
            return text("Give a journal's title, the start of it, or an ISSN.", error=True)
        registry = opened()
        if isinstance(registry, CallToolResult):
            return registry
        journals = registry.search(words, SEARCH_LIMIT)
        listed = "; ".join(_summary(j) for j in journals) or "none"
        where = registry.label or "the journal registry"
        return found(
            [document(j) for j in journals],
            f"{where}: {len(journals)} journal(s) for {words!r}: {listed}.",
        )

    return ToolRegistry(
        "journals",
        (GET_JOURNAL, SEARCH_JOURNALS),
        {"get_journal": get_journal, "search_journals": search_journals},
    )
