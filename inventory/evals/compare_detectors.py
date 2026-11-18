"""Compare personal-data detectors on the synthetic evaluation set (#39).

    uv run --with "en_core_web_sm @ $MODEL_WHEEL" python inventory/evals/compare_detectors.py

with `MODEL_WHEEL` the URL below (`--only presidio-patterns` needs no model; `--json` for JSON).

Each detector runs through the command's own check (`make_inventory` with `detector=`) on
`tests/data/disclosure`. Its findings in `evaluation/` are scored against `labels.json`:

- recall by kind;
- false positives on ordinary metadata;
- CPU time per 1,000 values;
- what it adds to the command, whether it runs in the browser, and its licences.

The scores are reported side by side and never blended (docs/specs/evaluation.md, invariant 4).
This is an evaluation, not a test: it sets no threshold, and pytest does not run it. It runs
offline once the spaCy model is installed, and never downloads one.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from importlib.metadata import PackageNotFoundError, distribution, version
from pathlib import Path
from typing import Any

from dd_inventory import make_inventory
from dd_inventory.personal import KINDS, Detector, Hit, PresidioDetector, recognisers

CORPUS = Path(__file__).parents[1] / "tests" / "data" / "disclosure"
EVALUATION = "evaluation/"
SPACY_MODEL = "en_core_web_sm"
MODEL_WHEEL = (
    "https://github.com/explosion/spacy-models/releases/download/"
    "en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl"
)
# What spaCy's entities are reported as, through Presidio's SpacyRecognizer.
NER_KINDS = {"PERSON": "person name", "LOCATION": "location"}
VALUE_TARGETS = ("column", "text")

Place = tuple[str, str, str | None]


class Timed:
    """A detector that counts the values it is given and the CPU time it takes over them."""

    def __init__(self, inner: Detector) -> None:
        self.inner = inner
        self.seconds = 0.0
        self.values = 0

    @property
    def description(self) -> str:
        return self.inner.description

    def analyse(self, text: str, context: Sequence[str]) -> list[Hit]:
        start = time.process_time()
        try:
            return self.inner.analyse(text, context)
        finally:
            self.seconds += time.process_time() - start
            self.values += text.count("\n") + 1


class SpacyDetector:
    """The command's recognisers with spaCy's named-entity recognition, for comparison only.

    Not shipped: whether the `pii-ner` extra runs it waits on this comparison."""

    def __init__(self, model: str = SPACY_MODEL) -> None:
        import spacy
        from presidio_analyzer import AnalyzerEngine, RecognizerRegistry
        from presidio_analyzer.nlp_engine import SpacyNlpEngine

        if not spacy.util.is_package(model):
            raise SystemExit(f"{model} is not installed: see this script's docstring")
        logging.getLogger("presidio-analyzer").setLevel(logging.ERROR)
        registry = RecognizerRegistry(supported_languages=["en"])
        for recogniser in recognisers():
            registry.add_recognizer(recogniser)
        engine = SpacyNlpEngine(models=[{"lang_code": "en", "model_name": model}])
        engine.load()
        # Presidio adds its spaCy recogniser only to a registry it makes itself.
        registry.add_nlp_recognizer(nlp_engine=engine)
        self._engine = AnalyzerEngine(
            registry=registry, nlp_engine=engine, supported_languages=["en"]
        )
        self._kinds = {**KINDS, **NER_KINDS}
        self._model = model

    @property
    def description(self) -> str:
        return (
            f"presidio-analyzer {version('presidio-analyzer')} with spaCy {version('spacy')} "
            f"and {self._model} {version(self._model)}"
        )

    def analyse(self, text: str, context: Sequence[str]) -> list[Hit]:
        results = self._engine.analyze(text, language="en", context=list(context) or None)
        return [
            Hit(self._kinds[r.entity_type], r.start, float(r.score))
            for r in results
            if r.entity_type in self._kinds
        ]


def place(case: Mapping[str, str]) -> Place:
    """Where a labelled case is: its file, what of it, and its column."""
    if "column" in case:
        return case["file"], "column", case["column"]
    return case["file"], case["target"], None


def score(findings: Iterable[Mapping[str, Any]], labels: Mapping[str, Any]) -> dict[str, Any]:
    """Recall by kind on the labelled places, the kinds found on the clean places, and the
    kinds found on labelled places besides those labelled there. A place counts once for a
    kind, however many findings it has."""
    found: dict[Place, set[str]] = defaultdict(set)
    for f in findings:
        if f["finding_target"] in VALUE_TARGETS:
            where = (f["finding_file"], f["finding_target"], f.get("finding_column"))
            found[where].add(f["finding_kind"])
    labelled: dict[Place, set[str]] = defaultdict(set)
    for case in labels["evaluation"]:
        labelled[place(case)].add(case["kind"])
    recall: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for case in labels["evaluation"]:
        tally = recall[case["kind"]]
        tally[0] += case["kind"] in found.get(place(case), set())
        tally[1] += 1
    besides: dict[str, int] = defaultdict(int)
    for where, kinds in labelled.items():
        for other in found.get(where, set()) - kinds:
            besides[other] += 1
    clean = [place(c) for c in labels["evaluation_clean"]]
    flagged = {p: sorted(found[p]) for p in clean if found.get(p)}
    return {
        "recall": {k: {"found": a, "labelled": n} for k, (a, n) in sorted(recall.items())},
        "needs_ner": sorted({c["kind"] for c in labels["evaluation"] if "needs" in c}),
        "false_positives": {
            "clean_places": len(clean),
            "flagged": [
                {"file": f, "target": t, "column": c, "kinds": kinds}
                for (f, t, c), kinds in sorted(flagged.items(), key=lambda i: str(i[0]))
            ],
        },
        "other_kinds_on_labelled_places": dict(sorted(besides.items())),
    }


def installed_bytes(names: Iterable[str]) -> int:
    """What the named distributions take on disk, as installed here."""
    total = 0
    for name in names:
        try:
            files = distribution(name).files or []
        except PackageNotFoundError:
            continue
        total += sum(f.size or 0 for f in files)
    return total


def licence(name: str) -> str:
    meta = distribution(name).metadata
    return str(meta.get("License-Expression") or meta.get("License") or "not stated")


def run(name: str, make: Callable[[], Detector], labels: Mapping[str, Any]) -> dict[str, Any]:
    """Make the detector, run the command's check with it, and score what it found."""
    start = time.process_time()
    timed = Timed(make())
    ready = time.process_time() - start
    inventory = make_inventory(CORPUS, detector=timed)
    findings = [
        f for f in inventory["inventory_personal_data"] if f["finding_file"].startswith(EVALUATION)
    ]
    return {
        "detector": name,
        "description": timed.description,
        **score(findings, labels),
        "cpu_seconds_to_start": round(ready, 2),
        "cpu_ms_per_1000_values": round(1000 * timed.seconds / max(timed.values, 1) * 1000, 1),
    }


DETECTORS: dict[str, tuple[Callable[[], Detector], dict[str, Any]]] = {
    "presidio-patterns": (
        PresidioDetector,
        {"adds": [], "browser": "yes", "licences": ["presidio-analyzer"]},
    ),
    "presidio-spacy": (
        SpacyDetector,
        {
            "adds": [SPACY_MODEL],
            "browser": "no",
            "licences": ["presidio-analyzer", "spacy", SPACY_MODEL],
        },
    ),
}


def markdown(results: list[dict[str, Any]]) -> str:
    """The results as one table, a row per measure and a column per detector."""
    names = [r["detector"] for r in results]
    rows = [f"| | {' | '.join(names)} |", "|---|" + "---|" * len(names)]
    kinds = sorted({k for r in results for k in r["recall"]})
    needs = set(results[0]["needs_ner"]) if results else set()
    for kind in kinds:
        label = f"Recall: {kind}{' (needs NER)' if kind in needs else ''}"
        cells = [f"{r['recall'][kind]['found']}/{r['recall'][kind]['labelled']}" for r in results]
        rows.append(f"| {label} | {' | '.join(cells)} |")
    fp = [
        f"{len(r['false_positives']['flagged'])}/{r['false_positives']['clean_places']}"
        for r in results
    ]
    rows.append(f"| Clean places flagged | {' | '.join(fp)} |")
    other = [
        ", ".join(f"{k} {n}" for k, n in r["other_kinds_on_labelled_places"].items()) or "none"
        for r in results
    ]
    rows.append(f"| Other kinds on labelled places | {' | '.join(other)} |")
    for key, label in (
        ("cpu_ms_per_1000_values", "CPU ms per 1,000 values"),
        ("cpu_seconds_to_start", "CPU s to start"),
        ("adds_mb", "Adds to the command (MB)"),
        ("browser", "Runs in the browser"),
        ("licences", "Licences"),
    ):
        rows.append(f"| {label} | {' | '.join(str(r[key]) for r in results)} |")
    return "\n".join(rows) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--json", action="store_true", help="write the results as JSON")
    parser.add_argument("--only", choices=sorted(DETECTORS), action="append")
    args = parser.parse_args(argv)
    labels = json.loads((CORPUS / "labels.json").read_text(encoding="utf-8"))
    import presidio_analyzer  # noqa: F401 - imported once here, so no detector's start pays for it

    results = []
    for name in args.only or DETECTORS:
        make, about = DETECTORS[name]
        result = run(name, make, labels)
        result["adds_mb"] = round(installed_bytes(about["adds"]) / 1e6, 1)
        result["browser"] = about["browser"]
        result["licences"] = ", ".join(f"{n}: {licence(n)}" for n in about["licences"])
        results.append(result)
    sys.stdout.write(json.dumps(results, indent=2) + "\n" if args.json else markdown(results))
    return 0


if __name__ == "__main__":
    sys.exit(main())
