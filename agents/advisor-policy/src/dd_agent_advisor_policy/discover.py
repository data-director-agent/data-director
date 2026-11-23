"""The first search beyond FAIRsharing: Open Policy Finder for funders, journals and publishers,
DOAJ for an open access journal's terms, and Crossref for the publisher a journal belongs to.
Fixed rules, never a guess.

- A **funder** is searched in Open Policy Finder by every name ROR gives it (or the name given),
  and a record is kept when one of its names or acronyms contains one of those names as whole
  words, as `match.fits` does for FAIRsharing.
- A **journal** is read by its ISSN when given, otherwise searched by its title, and a title is
  kept only when it is the same title once case, punctuation, "&" and a leading "The" are set
  aside. Two or more journals with that title are not guessed between: the researcher is asked,
  as for an ambiguous funder (#905). DOAJ is read the same way, with no key (#1517); it lists
  open access journals only. The journal's publishers are then read: Open Policy Finder links a
  journal to its publishers' records, and DOAJ or Crossref names the publisher when Open Policy
  Finder has no record of the journal. The publisher's name is searched in FAIRsharing too, so a
  journal with no policy of its own reaches its publisher's.

A registry that cannot be asked is noted and the search goes on: FAIRsharing still answers.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field

from dd_agent_advisor_policy.classes import Actor
from dd_agent_advisor_policy.crossref import CrossrefJournal, CrossrefJournals
from dd_agent_advisor_policy.doaj import DoajJournal, DoajJournals
from dd_agent_advisor_policy.opf import OpenPolicyFinder, OpfRecord
from dd_journals import normal_issn
from dd_sdk.registry import RegistryUnavailable

# Records kept for one actor from Open Policy Finder, as from FAIRsharing (match.PER_ACTOR).
PER_ACTOR = 3
# Names of one actor searched in Open Policy Finder: the name given and ROR's first few.
NAMES_SEARCHED = 4
# A company's legal form, which a publisher's policy record seldom repeats ("Elsevier BV").
# A journal's record in any registry that identifies journals.
JournalRecord = OpfRecord | CrossrefJournal | DoajJournal
LEGAL_FORM = re.compile(
    r"(?:[\s,]+(?:b\.?v\.?|ltd\.?|limited|inc\.?|gmbh|llc|plc|s\.a\.|ag|co\.?))+$", re.IGNORECASE
)


def title_key(title: str) -> str:
    """A title with case, punctuation, "&" and a leading "The" set aside."""
    text = title.casefold().replace("&", " and ")
    text = re.sub(r"[^\w\s]", " ", text)
    words = text.split()
    if words and words[0] == "the":
        words = words[1:]
    return " ".join(words)


def publisher_names(name: str) -> list[str]:
    """The publisher's name, and the same without its legal form."""
    plain = LEGAL_FORM.sub("", name.strip()).strip(" ,")
    return [n for n in dict.fromkeys((name.strip(), plain)) if n]


def names_one_of(record: OpfRecord, names: Sequence[str]) -> bool:
    """Whether one of the record's names or acronyms contains one of `names` as whole words."""
    for name in names:
        wanted = re.compile(rf"(?<!\w){re.escape(name.casefold().strip())}(?!\w)")
        if any(wanted.search(n) for n in record.all_names()):
            return True
    return False


def funders(
    actor: Actor, names: Sequence[str], opf: OpenPolicyFinder
) -> tuple[list[OpfRecord], list[str]]:
    """The Open Policy Finder funder records for one funder, and the queries made. Raises
    RegistryUnavailable."""
    wanted = list(dict.fromkeys(names or [actor.name]))[:NAMES_SEARCHED]
    found: dict[str, OpfRecord] = {}
    for name in wanted:
        for record in opf.search("funder", name):
            if names_one_of(record, wanted):
                found.setdefault(record.id, record)
    kept = sorted(found.values(), key=lambda r: (len(r.name), r.id))
    return kept[:PER_ACTOR], [f"open policy finder funder: {n!r}" for n in wanted]


@dataclass
class Journal:
    """What the first search found about one journal."""

    record: OpfRecord | None = None
    crossref: CrossrefJournal | None = None
    doaj: DoajJournal | None = None
    publishers: list[OpfRecord] = field(default_factory=list)
    publisher_names: list[str] = field(default_factory=list)
    # Two or more journals with the title given: the researcher is asked which.
    candidates: list[JournalRecord] = field(default_factory=list)
    queries: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)

    @property
    def publisher(self) -> str | None:
        if self.publishers:
            return self.publishers[0].name
        for other in (self.doaj, self.crossref):
            if other and other.publisher:
                return other.publisher
        return self.publisher_names[0] if self.publisher_names else None

    @property
    def issn(self) -> str | None:
        for issns in (
            self.record.issns if self.record else [],
            self.doaj.issns if self.doaj else [],
            self.crossref.issns if self.crossref else [],
        ):
            if issns:
                return issns[0]
        return None


def _same_title[T: JournalRecord](found: Sequence[T], title: str) -> list[T]:
    key = title_key(title)
    return [j for j in found if any(title_key(n) == key for n in _titles(j))]


def _titles(journal: JournalRecord) -> list[str]:
    if isinstance(journal, OpfRecord):
        return journal.names
    return journal.titles if isinstance(journal, DoajJournal) else [journal.title]


def _from_opf(out: Journal, actor: Actor, issn: str | None, opf: OpenPolicyFinder) -> bool:
    """The journal's Open Policy Finder record and its publishers'. True when the title is
    ambiguous, and the search stops for the researcher to say which."""
    try:
        if issn:
            out.queries.append(f"open policy finder journal: ISSN {issn}")
            out.record = opf.journal_by_issn(issn)
        else:
            out.queries.append(f"open policy finder journal: {actor.name!r}")
            same = _same_title(opf.search("publication", actor.name), actor.name)
            if len(same) > 1:
                out.candidates = list(same)
                return True
            out.record = same[0] if same else None
        for link in (out.record.publishers if out.record else [])[:PER_ACTOR]:
            publisher = opf.fetch("publisher", link.id)
            if publisher is not None:
                out.publishers.append(publisher)
    except RegistryUnavailable as exc:
        out.problems.append(str(exc))
    return False


def _from_doaj(out: Journal, actor: Actor, issn: str | None, doaj: DoajJournals) -> bool:
    """The journal's DOAJ record, which states its open access terms and names its publisher.
    True when DOAJ lists more than one journal of the title and Open Policy Finder did not say
    which: the search stops."""
    try:
        if issn:
            out.queries.append(f"doaj journal: ISSN {issn}")
            out.doaj = doaj.by_issn(issn)
        else:
            out.queries.append(f"doaj journal: {actor.name!r}")
            titled = _same_title(doaj.search(actor.name), actor.name)
            if len(titled) > 1 and out.record is None:
                out.candidates = list(titled)
                return True
            out.doaj = titled[0] if titled else None
    except RegistryUnavailable as exc:
        out.problems.append(str(exc))
    return False


def _from_crossref(
    out: Journal, actor: Actor, issn: str | None, crossref: CrossrefJournals
) -> bool:
    """The journal's Crossref record, which names its publisher. True when journals of the title
    have different publishers and neither Open Policy Finder nor DOAJ said which: the search
    stops."""
    try:
        if issn:
            out.queries.append(f"crossref journal: ISSN {issn}")
            out.crossref = crossref.by_issn(issn)
        else:
            out.queries.append(f"crossref journal: {actor.name!r}")
            titled = _same_title(crossref.search(actor.name), actor.name)
            if len({j.publisher for j in titled}) > 1 and not (out.record or out.doaj):
                out.candidates = list(titled)
                return True
            out.crossref = titled[0] if titled else None
    except RegistryUnavailable as exc:
        out.problems.append(str(exc))
    return False


def _collect_publisher_names(out: Journal) -> None:
    """Every name the registries give the journal's publishers, with and without legal form."""
    names: list[str] = []
    for publisher in out.publishers:
        names += publisher.names
    for other in (out.doaj, out.crossref):
        if other and other.publisher:
            names.append(other.publisher)
    for link in out.record.publishers if out.record else []:
        if link.name:
            names.append(link.name)
    out.publisher_names = list(dict.fromkeys(n for name in names for n in publisher_names(name)))


def _opf_publisher(out: Journal, opf: OpenPolicyFinder) -> None:
    """The publisher's Open Policy Finder record, searched by the name another registry gave."""
    try:
        plain = out.publisher_names[-1]
        out.queries.append(f"open policy finder publisher: {plain!r}")
        found = [p for p in opf.search("publisher", plain) if names_one_of(p, [plain])]
        out.publishers = sorted(found, key=lambda r: (len(r.name), r.id))[:1]
    except RegistryUnavailable as exc:
        out.problems.append(str(exc))


def journal(
    actor: Actor,
    opf: OpenPolicyFinder | None,
    crossref: CrossrefJournals | None,
    doaj: DoajJournals | None = None,
) -> Journal:
    """The journal's record, its publishers, or the candidates when the title is ambiguous.
    Never raises: a registry that cannot be asked is in `problems`."""
    out = Journal()
    issn = normal_issn(actor.issn) if actor.issn else None
    if opf is not None and _from_opf(out, actor, issn, opf):
        return out
    if doaj is not None and _from_doaj(out, actor, issn, doaj):
        return out
    if crossref is not None and not out.publishers and _from_crossref(out, actor, issn, crossref):
        return out
    _collect_publisher_names(out)
    # Crossref named the publisher but Open Policy Finder's journal record did not link it.
    if opf is not None and not out.publishers and out.publisher_names:
        _opf_publisher(out, opf)
    return out
