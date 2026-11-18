"""Look for possible personal data where the command already reads, and say where, never what
(docs/specs/personal-data.md).

Three places are checked: the values of each table's sampled rows, column by column; field, file
and folder names; and small `.txt` and `.md` files. The values come from the sample Frictionless
reads to infer a table's fields (`dd_inventory.tables`), so no file is read twice.

The detector is Microsoft Presidio with its pattern recognisers only, behind the `Detector`
protocol, so that another can replace it without touching the scan. It runs offline and loads
no language model, so names and places in values are not found: column headers and names stand
in for them. A finding holds a kind, a place, bands and the detector; never a value, part of one,
an offset, a row number or an example.
"""

from __future__ import annotations

import json
import logging
import re
from bisect import bisect_right
from collections.abc import Sequence
from dataclasses import dataclass, field
from functools import cache
from importlib.metadata import version
from importlib.resources import files
from pathlib import Path, PurePosixPath
from typing import Any, Protocol

from dd_inventory.tables import SAMPLE_ROWS, Table

TEXT_SUFFIXES = frozenset({".txt", ".md"})
TEXT_LIMIT = 256 * 1024  # bytes; a larger text file is not read
NAMES = "dd-inventory keyword table for field, file and folder names"

# Presidio's entity types, and the kind each is reported as.
KINDS = {
    "EMAIL_ADDRESS": "email address",
    "PHONE_NUMBER": "phone number",
    "UK_NHS": "NHS number",
    "UK_NINO": "National Insurance number",
    "UK_POSTCODE": "postcode",
    "UK_PASSPORT": "passport number",
    "UK_DRIVING_LICENCE": "driving licence number",
    "IBAN_CODE": "bank account number",
    "CREDIT_CARD": "payment card number",
    "IP_ADDRESS": "IP address",
}


@dataclass(frozen=True)
class Hit:
    """One match in a text: what it was taken for, where it starts, and the detector's score.
    `start` is used only to count matching rows; it is never written."""

    kind: str
    start: int
    score: float


class Detector(Protocol):
    """Finds possible personal data in a text. `context` holds words that say what the text is,
    such as a column header's, which a detector may use to raise its confidence."""

    @property
    def description(self) -> str: ...

    def analyse(self, text: str, context: Sequence[str]) -> list[Hit]: ...


def confidence_band(score: float) -> str:
    """A band of a detector's score: low below 0.5, Presidio's own threshold, medium below 0.85,
    high from 0.85. A low score is reported, not dropped (docs/specs/personal-data.md)."""
    if score >= 0.85:
        return "high"
    return "medium" if score >= 0.5 else "low"


def proportion_band(matched: int, examined: int) -> str:
    """The share of examined values that matched, as a band, so it cannot be turned into a count."""
    share = 100 * matched / examined if examined else 0
    if share < 1:
        return "under 1%"
    if share <= 10:
        return "1 to 10%"
    return "10 to 50%" if share <= 50 else "over 50%"


def words(name: str) -> list[str]:
    """A name's words: split on anything but letters, in lower case."""
    return [w for w in re.split(r"[^a-z]+", name.lower()) if w]


@cache
def keywords() -> dict[str, frozenset[str]]:
    """The keyword table, by category (`keywords.json`, a copy of advisor.ethics's)."""
    table = json.loads(files("dd_inventory").joinpath("keywords.json").read_text("utf-8"))
    return {category: frozenset(kws) for category, kws in table.items() if category[0] != "_"}


def name_categories(name: str) -> list[str]:
    """The categories of the keyword table a name falls in, in the table's order."""
    found = set(words(name))
    return [category for category, kws in keywords().items() if found & kws]


class PresidioDetector:
    """Presidio's pattern, checksum and context recognisers, with no language model.

    The UK recognisers, off in Presidio by default, are on; those for United States identifiers,
    which misread UK postcodes and National Insurance numbers, are left out. Two recognisers of
    the shape alone, of a National Insurance number and of a postcode, score low unless a column
    header says what the column holds, so values outside the allocated ranges are still found.
    The e-mail recogniser uses only the public-suffix list bundled with `tldextract`."""

    def __init__(self) -> None:
        from presidio_analyzer import AnalyzerEngine, RecognizerRegistry
        from presidio_analyzer.nlp_engine import NoOpNlpEngine

        logging.getLogger("presidio-analyzer").setLevel(logging.ERROR)
        registry = RecognizerRegistry(supported_languages=["en"])
        recognisers = _recognisers()
        for recogniser in recognisers:
            registry.add_recognizer(recogniser)
        self._names = sorted({str(getattr(r, "name", type(r).__name__)) for r in recognisers})
        self._engine = AnalyzerEngine(
            registry=registry,
            nlp_engine=NoOpNlpEngine(models=[{"lang_code": "en", "model_name": "none"}]),
            supported_languages=["en"],
        )

    @property
    def description(self) -> str:
        return (
            f"presidio-analyzer {version('presidio-analyzer')}, pattern recognisers only "
            f"({', '.join(self._names)})"
        )

    def analyse(self, text: str, context: Sequence[str]) -> list[Hit]:
        results = self._engine.analyze(text, language="en", context=list(context) or None)
        return [
            Hit(KINDS[r.entity_type], r.start, float(r.score))
            for r in results
            if r.entity_type in KINDS
        ]


def _recognisers() -> list[Any]:
    import tldextract
    from presidio_analyzer import Pattern, PatternRecognizer
    from presidio_analyzer import predefined_recognizers as pr

    offline = tldextract.TLDExtract(suffix_list_urls=(), cache_dir=None)

    class OfflineEmailRecognizer(pr.EmailRecognizer):
        def validate_result(self, pattern_text: str) -> bool:
            return bool(offline(pattern_text).fqdn)

    return [
        OfflineEmailRecognizer(),
        pr.PhoneRecognizer(supported_regions=("GB",)),
        pr.NhsRecognizer(),
        pr.UkNinoRecognizer(),
        pr.UkPostcodeRecognizer(),
        pr.UkPassportRecognizer(),
        pr.UkDrivingLicenceRecognizer(),
        pr.IbanRecognizer(),
        pr.CreditCardRecognizer(),
        pr.IpRecognizer(),
        PatternRecognizer(
            supported_entity="UK_NINO",
            name="UkNinoShapeRecognizer",
            patterns=[
                Pattern("NINO shape", r"\b[A-Za-z]{2} ?\d{2} ?\d{2} ?\d{2} ?[A-Da-d]\b", 0.3)
            ],
            context=["national", "insurance", "ni", "nino"],
        ),
        PatternRecognizer(
            supported_entity="UK_POSTCODE",
            name="UkPostcodeShapeRecognizer",
            patterns=[
                Pattern("postcode shape", r"\b[A-Za-z]{1,2}\d[A-Za-z\d]? ?\d[A-Za-z]{2}\b", 0.2)
            ],
            context=["postcode", "post", "code", "address", "home"],
        ),
        PatternRecognizer(
            supported_entity="PHONE_NUMBER",
            name="UkPhoneShapeRecognizer",
            patterns=[Pattern("UK phone shape", r"(?<![\w.])(?:\+44 ?|0)\d(?: ?\d){8,9}\b", 0.3)],
            context=["phone", "telephone", "tel", "mobile", "contact"],
        ),
    ]


@cache
def default_detector() -> Detector:
    """The detector the command uses unless told otherwise, made once per process."""
    return PresidioDetector()


@dataclass(frozen=True)
class Place:
    """Where a finding is: a file (or a folder, ending in a slash), what of it, and the column."""

    file: str
    target: str
    column: str | None = None

    def slots(self, kind: str) -> dict[str, str]:
        found = {"finding_kind": kind, "finding_file": self.file, "finding_target": self.target}
        if self.column is not None:
            found["finding_column"] = self.column
        return found


@dataclass
class Check:
    """The personal-data check of one scan: call `table`, `text` and `name` as files are read,
    then read `findings` and `limitations`."""

    detector: Detector
    findings: list[dict[str, Any]] = field(default_factory=list)
    _folders: set[str] = field(default_factory=set)
    _too_large: int = 0

    def name(self, relative: PurePosixPath) -> None:
        """Check the file's name, and the name of each folder it is in not checked before."""
        for depth in range(1, len(relative.parts)):
            folder = "/".join(relative.parts[:depth])
            if folder not in self._folders:
                self._folders.add(folder)
                self._names(Place(f"{folder}/", "file name"), relative.parts[depth - 1])
        self._names(Place(str(relative), "file name"), relative.name)

    def table(self, relative: str, table: Table) -> None:
        """Check each column's header and its sampled values."""
        for column, values in table.columns.items():
            self._names(Place(relative, "field name", column), column)
            if values:
                self._column(relative, column, values)

    def text(self, path: Path, relative: str) -> None:
        """Check a small text file's text; count a large one as not checked."""
        if PurePosixPath(relative).suffix.lower() not in TEXT_SUFFIXES:
            return
        if path.stat().st_size > TEXT_LIMIT:
            self._too_large += 1
            return
        text = path.read_bytes().decode("utf-8", errors="replace")
        best: dict[str, float] = {}
        for hit in self.detector.analyse(text, ()):
            best[hit.kind] = max(hit.score, best.get(hit.kind, 0.0))
        for kind, score in best.items():
            self._add(kind, Place(relative, "text"), confidence_band(score), examined=len(text))

    def limitations(self) -> list[str]:
        """What the check looked for and what it did not, in the spec's substance."""
        said = [
            f"Possible personal data were looked for with {self.detector.description}: in the "
            f"values of up to {SAMPLE_ROWS} sampled rows of each CSV or TSV table, in field, file "
            "and folder names, and in .txt and .md files of at most 256 KB. Names and places "
            "were looked for in column headers and names only, not in values. Other formats, "
            "indirect identifiers and rows beyond the sample were not checked, so finding "
            "nothing does not mean the data hold no personal data."
        ]
        if self._too_large:
            said.append(
                f"{self._too_large} text file(s) over 256 KB were not checked for personal data."
            )
        return said

    def sorted_findings(self) -> list[dict[str, Any]]:
        def key(f: dict[str, Any]) -> tuple[str, ...]:
            return (
                f["finding_file"],
                f["finding_target"],
                f.get("finding_column", ""),
                f["finding_kind"],
            )

        return sorted(self.findings, key=key)

    def _column(self, relative: str, column: str, values: list[str]) -> None:
        text = "\n".join(v.replace("\n", " ") for v in values)
        starts = [0]
        for value in values[:-1]:
            starts.append(starts[-1] + len(value) + 1)
        rows: dict[str, set[int]] = {}
        best: dict[str, float] = {}
        for hit in self.detector.analyse(text, words(column)):
            rows.setdefault(hit.kind, set()).add(bisect_right(starts, hit.start) - 1)
            best[hit.kind] = max(hit.score, best.get(hit.kind, 0.0))
        for kind, matched in rows.items():
            self._add(
                kind,
                Place(relative, "column", column),
                confidence_band(best[kind]),
                proportion=proportion_band(len(matched), len(values)),
                examined=len(values),
            )

    def _names(self, place: Place, name: str) -> None:
        for category in name_categories(name):
            self.findings.append(
                {**place.slots(category), "finding_confidence": "medium", "finding_detector": NAMES}
            )

    def _add(self, kind: str, place: Place, confidence: str, **measured: Any) -> None:
        """Record a finding of the detector's. `measured` holds `proportion` and `examined`."""
        finding: dict[str, Any] = {**place.slots(kind)}
        if measured.get("proportion") is not None:
            finding["finding_proportion"] = measured["proportion"]
        finding["finding_confidence"] = confidence
        finding["finding_detector"] = self.detector.description
        finding["finding_examined"] = measured["examined"]
        self.findings.append(finding)
