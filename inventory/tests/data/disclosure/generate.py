"""Generate the synthetic disclosure corpus (docs/specs/personal-data.md, #610).

Every value is invented, from ranges kept for fiction or testing, so the corpus holds no real
personal data:

- e-mail addresses at `example.org`, `example.com` and `example.net` (RFC 2606);
- telephone numbers from Ofcom's ranges for drama: `07700 900000` to `07700 900999` and
  `020 7946 0000` to `020 7946 0999`;
- NHS numbers beginning `999`, a range the NHS never issues, with a valid check digit so that a
  checksum-validating recogniser still matches them;
- National Insurance numbers with the prefix `QQ`, which is never allocated;
- full postcodes in `ZZ99`, the NHS pseudo-postcode area, and postcode districts with no
  address attached;
- names put together from short lists of common given names and surnames, and addresses on
  invented streets in invented places;
- DOIs under `10.5555`, the prefix kept for examples, and ISBNs under `979-8-0000`.

The tables and files are written below this folder, and `labels.json` says what each case
should produce: a personal-data finding, a suppressed summary value or a quasi-identifier
referral. Clean controls of the same shape say what should produce nothing. `evaluation/` is a
larger set for comparing personal-data detectors (#39): several columns and texts of each kind,
some under headers that say nothing, and ordinary research metadata that should produce nothing.

Run it from the repository root to rewrite the corpus, and commit what it writes:

    uv run python inventory/tests/data/disclosure/generate.py

The output depends only on the seed, so a test checks the committed files against it.
"""

from __future__ import annotations

import csv
import io
import json
import random
import sys
from collections.abc import Callable, Sequence
from datetime import date, timedelta
from pathlib import Path

SEED = 610
ROWS = 200

GIVEN = ["Ana", "Ben", "Chloe", "Dev", "Ella", "Femi", "Grace", "Hamid", "Isla", "Jon", "Kiran"]
FAMILY = ["Smith", "Jones", "Patel", "Khan", "Taylor", "Brown", "Wilson", "Evans", "Ahmed", "Lee"]
DOMAINS = ["example.org", "example.com", "example.net"]
SITES = ["north", "south", "east", "west"]
DIAGNOSES = ["asthma", "eczema", "hay fever"]
STREETS = ["Larchwood", "Rowan Hey", "Fellside", "Mossbank", "Quarry Brow", "Tenterfield"]
PLACES = ["Easterby", "Westholme", "Low Fennick", "Ashby Parva", "Kettlewick"]
SPECIES = ["Numenius arquata", "Vanellus vanellus", "Calluna vulgaris", "Sphagnum capillifolium"]


def nhs_number(rng: random.Random) -> str:
    """A ten-digit NHS number beginning 999, never issued, with a valid modulus 11 check digit."""
    while True:
        digits = [9, 9, 9] + [rng.randrange(10) for _ in range(6)]
        remainder = sum(d * w for d, w in zip(digits, range(10, 1, -1), strict=True)) % 11
        check = 11 - remainder
        if check == 10:
            continue
        digits.append(0 if check == 11 else check)
        text = "".join(map(str, digits))
        return f"{text[:3]} {text[3:6]} {text[6:]}"


def ni_number(rng: random.Random) -> str:
    return f"QQ{rng.randrange(1_000_000):06d}{rng.choice('ABCD')}"


def mobile(rng: random.Random) -> str:
    return f"07700 900{rng.randrange(1000):03d}"


def landline(rng: random.Random) -> str:
    return f"020 7946 0{rng.randrange(1000):03d}"


UNIT_LETTERS = "ABDEFGHJLNPQRSTUWXYZ"


def pseudo_postcode(rng: random.Random) -> str:
    return f"ZZ99 {rng.randrange(10)}{rng.choice(UNIT_LETTERS)}{rng.choice(UNIT_LETTERS)}"


def name(rng: random.Random) -> tuple[str, str]:
    return rng.choice(GIVEN), rng.choice(FAMILY)


def full_name(rng: random.Random) -> str:
    return " ".join(name(rng))


def email(rng: random.Random) -> str:
    given, family = name(rng)
    return f"{given.lower()}.{family.lower()}{rng.randrange(100)}@{rng.choice(DOMAINS)}"


def phone(rng: random.Random) -> str:
    """A number from Ofcom's ranges for drama, written as people write them."""
    number = mobile(rng) if rng.random() < 0.6 else landline(rng)
    return "+44 " + number[1:] if rng.random() < 0.3 else number


def serial(rng: random.Random) -> str:
    """An instrument serial number: two groups of four digits and a check digit."""
    return f"SN {rng.randrange(1000, 10_000)}-{rng.randrange(1000, 10_000)}-{rng.randrange(10)}"


def address(rng: random.Random) -> str:
    return f"{rng.randrange(1, 120)} {rng.choice(STREETS)}, {rng.choice(PLACES)}"


def table(header: list[str], rows: Sequence[Sequence[object]], delimiter: str = ",") -> str:
    out = io.StringIO()
    writer = csv.writer(out, delimiter=delimiter, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(rows)
    return out.getvalue()


def direct(rng: random.Random) -> dict[str, str]:
    """Direct identifiers in values, in free text and in a file name, and a clean control."""
    rows = []
    for i in range(1, ROWS + 1):
        given, family = name(rng)
        rows.append(
            [
                f"P{i:04d}",
                f"{given.lower()}.{family.lower()}@{rng.choice(DOMAINS)}",
                mobile(rng) if rng.random() < 0.7 else landline(rng),
                nhs_number(rng),
                ni_number(rng),
                pseudo_postcode(rng),
                rng.choice(SITES),
            ]
        )
    participants = table(
        ["participant", "contact", "telephone", "nhs_no", "ni_no", "home", "site"], rows
    )
    given, family = name(rng)
    notes = (
        "Interview notes, session 3.\n\n"
        f"Spoke with {given} {family} about the second visit. "
        "They asked that the follow-up be sent "
        f"to {given.lower()}{rng.randrange(100)}@example.net, or by text to {mobile(rng)}.\n"
        "No change to the protocol was needed.\n"
    )
    consent_given, consent_family = name(rng)
    consent = "Consent form received and filed. Signature present on both pages.\n"
    clean = table(
        ["sample", "site", "depth_cm", "ph", "moisture_pct"],
        [
            [
                f"S{i:04d}",
                rng.choice(SITES),
                rng.choice([10, 20, 30, 40]),
                round(rng.uniform(5.0, 7.5), 1),
                round(rng.uniform(10, 45), 1),
            ]
            for i in range(1, ROWS + 1)
        ],
    )
    return {
        "direct/participants.csv": participants,
        "direct/interviews/notes.txt": notes,
        f"direct/consent/{consent_given.lower()}-{consent_family.lower()}-consent.txt": consent,
        "direct/clean/samples.csv": clean,
    }


def summaries(rng: random.Random) -> dict[str, str]:
    """A cohort with one extreme age, one extreme income, a rare category and a missing-value
    code, and a control of the same shape with none of them."""
    rows = []
    for i in range(1, ROWS + 1):
        age: object = rng.randint(25, 64)
        income: object = round(rng.gauss(31_000, 4_000), -2)
        diagnosis = rng.choice(DIAGNOSES)
        rows.append([f"C{i:04d}", age, income, diagnosis])
    rows[17][1] = 97  # one extreme age
    rows[42][2] = 412_000.0  # one extreme income
    rows[63][3] = "Fabry disease"  # rare categories, held by two people
    rows[151][3] = "Fabry disease"
    for i in rng.sample(range(ROWS), 30):  # a missing-value code, common enough to pass k
        if i not in (17, 42):
            rows[i][1] = -99
    cohort = table(["participant", "age", "income", "diagnosis"], rows)
    control_rows = [
        [
            f"K{i:04d}",
            rng.randint(25, 64),
            round(rng.gauss(31_000, 4_000), -2),
            rng.choice(DIAGNOSES),
        ]
        for i in range(1, ROWS + 1)
    ]
    control = table(["participant", "age", "income", "diagnosis"], control_rows)
    return {"summaries/cohort.csv": cohort, "summaries/cohort-control.csv": control}


def quasi(rng: random.Random) -> dict[str, str]:
    """A survey in which age, sex, postcode district and visit date single out records, and a
    control whose candidate columns are coarse enough that every group holds ten or more."""
    start = date(2024, 1, 1)
    rows = []
    for i in range(1, ROWS + 1):
        rows.append(
            [
                f"R{i:04d}",
                rng.randint(18, 90),
                rng.choice(["female", "male"]),
                f"S{rng.randint(1, 35)}",
                (start + timedelta(days=rng.randrange(365))).isoformat(),
                rng.randint(1, 5),
            ]
        )
    survey = table(["respondent", "age", "sex", "district", "visit_date", "score"], rows, "\t")
    control_rows = [
        [
            f"Q{i:04d}",
            rng.choice(["18-39", "40-64", "65+"]),
            rng.choice(["female", "male"]),
            rng.choice(["north", "south"]),
            rng.choice(["2024-H1", "2024-H2"]),
            rng.randint(1, 5),
        ]
        for i in range(1, ROWS + 1)
    ]
    control = table(
        ["respondent", "age_band", "sex", "region", "visit_half", "score"], control_rows, "\t"
    )
    return {"quasi/survey.tsv": survey, "quasi/survey-control.tsv": control}


# The evaluation set's tables: file, then each column as (header, kind, value). A kind of None is
# ordinary metadata. Names and places ("needs NER") only named-entity recognition finds in values.
NER = "needs NER"
EVALUATION_TABLES: dict[str, list[tuple[str, str | None, str]]] = {
    "evaluation/registrations.csv": [
        ("ref", None, "ref"),
        ("full_name", "person name", "full_name"),
        ("email", "email address", "email"),
        ("mobile", "phone number", "phone"),
        ("home_address", "location", "address"),
    ],
    "evaluation/followup.tsv": [
        ("col1", "email address", "email"),
        ("col2", "phone number", "phone"),
        ("col3", "NHS number", "nhs_number"),
        ("col4", "National Insurance number", "ni_number"),
        ("col5", "postcode", "pseudo_postcode"),
        ("col6", "person name", "full_name"),
    ],
    "evaluation/contacts.csv": [
        ("contact_2", "phone number", "phone"),
        ("addr", "location", "address"),
        ("pc", "postcode", "pseudo_postcode"),
        ("who", "person name", "full_name"),
    ],
    "evaluation/specimens.csv": [
        ("specimen_id", None, "specimen"),
        ("instrument_serial", None, "serial"),
        ("doi", None, "doi"),
        ("isbn", None, "isbn"),
        ("mass_g", None, "mass"),
        ("collected", None, "collected"),
        ("site_code", None, "site_code"),
        ("species", None, "species"),
    ],
}
NEEDS_NER = {"person name", "location"}


def _values(rng: random.Random) -> dict[str, Callable[[], str]]:
    """How each column's values are made, by the name the tables give."""
    return {
        "ref": lambda: f"R{rng.randrange(10_000):04d}",
        "full_name": lambda: full_name(rng),
        "email": lambda: email(rng),
        "phone": lambda: phone(rng),
        "address": lambda: address(rng),
        "nhs_number": lambda: nhs_number(rng),
        "ni_number": lambda: ni_number(rng),
        "pseudo_postcode": lambda: pseudo_postcode(rng),
        "specimen": lambda: f"SPC-{rng.randrange(2019, 2026)}-{rng.randrange(10_000):04d}",
        "serial": lambda: serial(rng),
        "doi": lambda: f"10.5555/moor.{rng.randrange(10_000)}",
        "isbn": lambda: f"979-8-0000-{rng.randrange(1000, 9999)}-{rng.randrange(10)}",
        "mass": lambda: f"{rng.uniform(0.1, 250):.2f}",
        "collected": lambda: (date(2024, 3, 1) + timedelta(days=rng.randrange(200))).isoformat(),
        "site_code": lambda: f"NX-{rng.randrange(1, 40):02d}",
        "species": lambda: rng.choice(SPECIES),
    }


def evaluation(rng: random.Random) -> dict[str, str]:
    """Tables and texts for comparing detectors: each kind in several columns, and negatives."""
    make = _values(rng)
    files = {}
    for path, columns in EVALUATION_TABLES.items():
        rows = [[make[value]() for _, _, value in columns] for _ in range(ROWS)]
        delimiter = "\t" if path.endswith(".tsv") else ","
        files[path] = table([header for header, _, _ in columns], rows, delimiter)
    for i in range(1, 6):
        files[f"evaluation/notes/visit-{i:02d}.txt"] = (
            f"Visit {i}. Met {full_name(rng)} at the field station to go over the consent form. "
            f"Reminders go to {email(rng)}; on the day, call {phone(rng)}.\n"
        )
    files["evaluation/notes/methods.md"] = (
        "# Methods\n\nCores were taken at 10 cm intervals and weighed wet, then dried at 105 C "
        "for 24 hours. Species were recorded on a 2 m quadrat at each site code.\n"
    )
    return files


def evaluation_labels() -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Each place a detector should flag, with its kind, and each place it should not."""
    found: list[dict[str, str]] = []
    clean: list[dict[str, str]] = []
    for path, columns in EVALUATION_TABLES.items():
        for header, kind, _ in columns:
            if kind is None:
                clean.append({"file": path, "column": header})
                continue
            case = {"file": path, "column": header, "kind": kind}
            found.append({**case, "needs": NER} if kind in NEEDS_NER else case)
    for i in range(1, 6):
        text = {"file": f"evaluation/notes/visit-{i:02d}.txt", "target": "text"}
        found += [
            {**text, "kind": "email address"},
            {**text, "kind": "phone number"},
            {**text, "kind": "person name", "needs": NER},
        ]
    clean.append({"file": "evaluation/notes/methods.md", "target": "text"})
    return found, clean


def labels(files: dict[str, str]) -> dict[str, object]:
    """What each case should produce. A file or column not listed should produce nothing."""
    consent = next(p for p in files if p.startswith("direct/consent/"))
    return {
        "seed": SEED,
        "personal_data": [
            {"file": "direct/participants.csv", "column": "contact", "kind": "email address"},
            {"file": "direct/participants.csv", "column": "telephone", "kind": "phone number"},
            {"file": "direct/participants.csv", "column": "nhs_no", "kind": "NHS number"},
            {
                "file": "direct/participants.csv",
                "column": "ni_no",
                "kind": "National Insurance number",
            },
            {"file": "direct/participants.csv", "column": "home", "kind": "postcode"},
            {"file": "direct/interviews/notes.txt", "target": "text", "kind": "email address"},
            {"file": "direct/interviews/notes.txt", "target": "text", "kind": "phone number"},
            {
                "file": "direct/interviews/notes.txt",
                "target": "text",
                "kind": "person name",
                "needs": "a spaCy model",
            },
            {
                "file": consent,
                "target": "file name",
                "kind": "person name",
                "needs": "a spaCy model",
            },
        ],
        "suppressed": [
            {"file": "summaries/cohort.csv", "column": "age", "what": "raw maximum"},
            {"file": "summaries/cohort.csv", "column": "income", "what": "raw maximum"},
            {"file": "summaries/cohort.csv", "column": "diagnosis", "what": "rare category"},
        ],
        "kept": [
            {"file": "summaries/cohort.csv", "column": "age", "what": "missing-value code -99"},
        ],
        "quasi_identifier": [
            {
                "file": "quasi/survey.tsv",
                "columns": ["age", "sex", "district", "visit_date"],
                "refer": True,
            },
            {
                "file": "quasi/survey-control.tsv",
                "columns": ["age_band", "sex", "region", "visit_half"],
                "refer": False,
            },
        ],
        "clean": [
            "direct/clean/samples.csv",
            "summaries/cohort-control.csv",
            "quasi/survey-control.tsv",
        ],
        "evaluation": evaluation_labels()[0],
        "evaluation_clean": evaluation_labels()[1],
    }


def corpus() -> dict[str, str]:
    """Every file of the corpus, by path relative to this folder, with `labels.json`."""
    rng = random.Random(SEED)
    files = {**direct(rng), **summaries(rng), **quasi(rng), **evaluation(rng)}
    files["labels.json"] = json.dumps(labels(files), indent=2) + "\n"
    return files


def write(root: Path) -> None:
    for relative, text in corpus().items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="")


if __name__ == "__main__":
    write(Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent)
