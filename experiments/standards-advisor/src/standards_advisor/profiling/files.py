"""File format detection — §5.1 tier 1, and the input to the R3.3 search.

Two signals, and the profile records which one decided. That matters because they disagree in
informative ways: a `.csv` whose leading bytes are a zip container is not a CSV, and a reader of
the run should be able to see that the extension was overruled rather than wonder.
"""

from __future__ import annotations

from pathlib import Path

from standards_advisor.models.common import Derivation

# Bytes read to look for a signature. Every signature below is far shorter than this.
MAGIC_READ_BYTES = 16

EXTENSION_FORMATS: dict[str, str] = {
    ".csv": "csv",
    ".tsv": "tsv",
    ".tab": "tsv",
    ".txt": "txt",
    ".json": "json",
    ".jsonl": "jsonl",
    ".ndjson": "jsonl",
    ".xml": "xml",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".parquet": "parquet",
    ".xlsx": "xlsx",
    ".xlsm": "xlsx",
    ".ods": "ods",
    ".xls": "xls",
    ".nc": "netcdf",
    ".cdf": "netcdf",
    ".h5": "hdf5",
    ".hdf5": "hdf5",
    ".sav": "spss",
    ".dta": "stata",
    ".sas7bdat": "sas",
    ".rds": "rds",
    ".zip": "zip",
    ".pdf": "pdf",
    ".docx": "docx",
    ".shp": "shapefile",
    ".geojson": "geojson",
}

# Signatures, longest first so a longer match is not shadowed by a shorter prefix.
MAGIC_SIGNATURES: tuple[tuple[bytes, str], ...] = (
    (b"\x89HDF\r\n\x1a\n", "hdf5"),
    (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1", "ole2"),
    (b"%PDF-", "pdf"),
    (b"PAR1", "parquet"),
    (b"PK\x03\x04", "zip_container"),
    (b"CDF\x01", "netcdf"),
    (b"CDF\x02", "netcdf"),
    (b"\x1f\x8b", "gzip"),
)

# A magic signature identifies a *container*; the extension often identifies what is inside it.
# Where the extension names a known specialisation of the detected container, the extension is
# the more informative answer and wins — but only then.
MAGIC_SPECIALISATIONS: dict[str, frozenset[str]] = {
    "zip_container": frozenset({"xlsx", "ods", "docx", "zip"}),
    "ole2": frozenset({"xls", "doc"}),
}

TABULAR_FORMATS: frozenset[str] = frozenset({"csv", "tsv", "txt"})


def detect_by_extension(path: Path) -> str | None:
    return EXTENSION_FORMATS.get(path.suffix.lower())


def detect_by_magic(head: bytes) -> str | None:
    for signature, label in MAGIC_SIGNATURES:
        if head.startswith(signature):
            return label
    return None


def read_magic(path: Path, size: int = MAGIC_READ_BYTES) -> bytes:
    with path.open("rb") as handle:
        return handle.read(size)


def resolve_format(path: Path) -> tuple[str | None, Derivation | None, list[str]]:
    """Return `(format, derivation, notes)` for one file.

    Precedence: a magic signature beats the extension, except where the extension names a
    known specialisation of the detected container — a `.xlsx` really is a zip, and calling it
    `zip_container` would be true but useless. A genuine disagreement is reported as the magic
    result plus a note, never silently resolved.
    """
    extension = detect_by_extension(path)
    magic = detect_by_magic(read_magic(path))
    notes: list[str] = []

    if magic is None:
        # Text formats have no signature. This is the normal path for CSV.
        return extension, (Derivation.FILE_EXTENSION if extension else None), notes

    specialisations = MAGIC_SPECIALISATIONS.get(magic, frozenset())
    if extension is not None and extension in specialisations:
        notes.append(f"extension {extension!r} is consistent with detected container {magic!r}")
        return extension, Derivation.FILE_EXTENSION, notes

    if extension is not None and extension != magic:
        notes.append(
            f"extension suggests {extension!r} but leading bytes indicate {magic!r}; "
            "the leading bytes were used"
        )

    return magic, Derivation.FILE_MAGIC, notes


def is_tabular(format_label: str | None) -> bool:
    return format_label in TABULAR_FORMATS
