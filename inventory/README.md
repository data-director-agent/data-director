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
  Table Schema inferred from a sample of rows.

The inventory holds facts about the files and never their content. Research data are not
uploaded to Data Director: the researcher adds the inventory to their project instead
([Projects](../docs/specs/projects.md)). The digests let the files deposited
later be shown to be the files described.

```console
$ uv run dd-inventory path/to/dataset -o inventory.json
```

The package installs two names for the same command, `dd-inventory` and `data-director-inventory`,
so that `uvx data-director-inventory path/to/dataset` works once the package is on PyPI (#552).
Until then it is published to TestPyPI only ([RELEASING.md](../RELEASING.md)).

A researcher without a checkout runs it with `uvx` and attaches the file to a conversation in the
app; the user guide's [Making an inventory](https://data-director-agent.github.io/data-director/user-guide/making-an-inventory/)
says how.

Hidden files and folders (names beginning with `.`) are skipped, symbolic links are not
followed, and both are counted in `inventory_limitations`. If fido cannot be loaded, formats are
guessed from file extensions and the inventory says so.

The package does not depend on the contract or any other part of Data Director
([System and boundaries](../docs/specs/system.md)). Its tests check
what it writes against the contract's `FileInventory` schema.

| Module | What it does |
|---|---|
| `scan.py` | Walks the folder, digests each file and assembles the inventory. |
| `identify.py` | The one module that calls fido, with the extension fallback. |
| `tables.py` | Infers a table's fields with Frictionless. |
| `cli.py` | The `dd-inventory` command. |
