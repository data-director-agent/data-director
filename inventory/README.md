# Data Director inventory

[![CI](https://github.com/data-director-agent/data-director/actions/workflows/ci.yml/badge.svg)](https://github.com/data-director-agent/data-director/actions/workflows/ci.yml) [![Coverage](https://codecov.io/gh/data-director-agent/data-director/graph/badge.svg?flag=inventory)](https://codecov.io/gh/data-director-agent/data-director?flags[0]=inventory)

`dd-inventory` describes a dataset's files where they live. It reads every file under a folder
and writes a `FileInventory`, a JSON document of the core contract, that gives for each file:

- its path relative to the folder;
- its size and its SHA-256 digest;
- its media type and every [PRONOM](https://www.nationalarchives.gov.uk/PRONOM/) identifier it
  matched, found with [fido](https://github.com/openpreserve/fido), and whether the match was by
  byte signature, container signature or extension only;
- for a CSV or TSV table, its fields as a [Frictionless](https://framework.frictionlessdata.io/)
  Table Schema inferred from a sample of rows, reading empty cells and `NA`, `N/A`, `NaN` and
  `null` as missing values, and saying in its limitations which markers it met and which fields
  had no value to type;
- for each field of such a table, summary values that passed statistical disclosure control:
  rows read, empty cells, a range, a mean, categories and missing-value codes (below);
- where it found possible personal data, and never what (below).

The inventory holds facts about the files and never their content. Research data are not
uploaded to Data Director: the researcher adds the inventory to their project instead
([Projects](https://github.com/data-director-agent/data-director/blob/main/docs/specs/projects.md)). The digests let the files deposited
later be shown to be the files described.

```console
$ uv run dd-inventory path/to/dataset -o inventory.json
```

Given several folders, it makes one inventory with a part for each
([Projects](https://github.com/data-director-agent/data-director/blob/main/docs/specs/projects.md)):
each folder's files are listed under its name, and each part keeps its own tool, time and
limitations. Two folders of the same name need names of their own, given with `--as` once for
each folder, in order. `make_inventory_of` does the same from Python.

```console
$ uv run dd-inventory raw processed -o inventory.json
$ uv run dd-inventory /lab/2024 /instrument/2024 --as lab --as instrument -o inventory.json
```

The package installs two names for the same command, `dd-inventory` and `data-director-inventory`,
so that `uvx data-director-inventory path/to/dataset` works. It is published to [PyPI](https://pypi.org/p/data-director-inventory) and, for trying a release first, TestPyPI ([RELEASING.md](https://github.com/data-director-agent/data-director/blob/main/RELEASING.md)).

A researcher without a checkout runs it with `uvx` and attaches the file to a conversation in the
app; the user guide's [Making an inventory](https://data-director-agent.github.io/data-director/user-guide/making-an-inventory/)
says how.

It looks for possible personal data in what it already reads: the values of each table's sampled
rows, column by column; field, file and folder names; and `.txt` and `.md` files of at most
256 KB ([Personal data and disclosure control](https://github.com/data-director-agent/data-director/blob/main/docs/specs/personal-data.md)).
The detector is [Presidio](https://github.com/data-privacy-stack/presidio) with its pattern recognisers
only, with the UK ones on (National Insurance number, NHS number, postcode, passport, driving
licence) and phone numbers read as UK numbers, plus a keyword table for names. It runs offline
and loads no language model, so names and places are looked for in column headers and names, not
in values. `inventory_personal_data` lists each finding: a kind, the file and column, the share
of sampled values that matched and a confidence, both as bands, and the detector. A finding never
holds a value, part of one, a row number or an example. An empty list means the detector found
nothing, which does not mean the data hold no personal data; the limitations say what was not
checked. `--no-detect` (or `detector=None`) skips the check, and the list is then absent, which
says no detector ran. Presidio installs spaCy, which the command does not use; the
`pii-ner` extra is for named-entity recognition later (#39).

```console
$ uv run dd-inventory path/to/dataset --no-detect -o inventory.json
```

Summary values let an agent describe a table's fields without seeing the data. They are made on
the researcher's computer, from up to 100,000 rows of each table, and written only if they pass
statistical disclosure control with [ACRO](https://github.com/AI-SDC/ACRO), the SACRO project's
output checker (MIT) ([Personal data and disclosure control](https://github.com/data-director-agent/data-director/blob/main/docs/specs/personal-data.md)):
every count is held by at least *k* rows (10 by default) and rounded to base 5; a range is the
*k*-th smallest and *k*-th largest values, never the minimum and maximum; a mean is left out if
one or two values dominate it; and a column where possible personal data were found gets no
categories. A value that fails is left out, never altered, and each field's
`field_disclosure_check` says how many. `--threshold` and `--rounding` tighten the rules and
refuse lower values; `--no-summaries` leaves them out. Summaries do not run in the browser, where
ACRO would add about 42 MB and 18 s before a scan, and the inventory says so.

```console
$ uv run dd-inventory path/to/dataset --threshold 20 -o inventory.json
```

`evals/compare_detectors.py` compares detectors on the synthetic evaluation set in
`tests/data/disclosure/evaluation/`: recall by kind, false positives on ordinary metadata, CPU
time and what each adds. Its result, and why the default runs pattern recognisers only, is in
[Personal data and disclosure control](https://github.com/data-director-agent/data-director/blob/main/docs/specs/personal-data.md#the-detector-comparison).

Hidden files and folders (names beginning with `.`) are skipped, symbolic links are not
followed, and both are counted in `inventory_limitations`. If fido cannot be loaded, formats are
guessed from file extensions and the inventory says so.

The same package runs in a web browser under [Pyodide](https://pyodide.org/), so that a researcher
can describe a folder without installing anything ([#367](https://github.com/data-director-agent/data-director/issues/367)). The inventory it makes there is the
command's, except that its `inventory_tool_version` carries a local version label naming the
runtime, such as `0.1.0a3+pyodide.314.0.7`; `inventory_tool` is `dd-inventory` in both. An
inventory whose version has no `+` label was made by the command. `make_inventory` detects the
runtime, and a caller may pass it in as `runtime=`. A caller may also pass `on_file=`, which is
called once per file with a `FileProgress` (its relative path and size, and how many of the
files are done), to show progress. The personal-data check runs there too, so the two find the
same. `browser/bundle/` builds the browser bundle (Pyodide, this package's wheel and its
dependencies, with a stand-in for spaCy), and CI checks that it writes the same inventory as the
command on `tests/data/mixed` ([browser bundle](https://github.com/data-director-agent/data-director/blob/main/inventory/browser/README.md#browser-bundle)).

To read an inventory in TypeScript, as the app does to show one to the researcher, use
[`@data-director/inventory`](https://github.com/data-director-agent/data-director/blob/main/inventory/browser/README.md) in `browser/`, which is not part of this Python
package.

The package does not depend on the contract or any other part of Data Director
([System and boundaries](https://github.com/data-director-agent/data-director/blob/main/docs/specs/system.md)). Its tests check
what it writes against the contract's `FileInventory` schema.

| Module | What it does |
|---|---|
| `scan.py` | Walks the folder, digests each file and assembles the inventory. |
| `identify.py` | The one module that calls fido, with the extension fallback. |
| `tables.py` | Infers a table's fields with Frictionless, keeping the sampled values for the check. |
| `summaries.py` | Computes table fields' summary values and checks them with ACRO, the one module that imports it. |
| `personal.py` | Looks for possible personal data with Presidio and the keyword table (`keywords.json`, a copy of advisor.ethics's). |
| `cli.py` | The `dd-inventory` command. |
