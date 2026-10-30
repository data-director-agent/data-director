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
([ADR-0034](../docs/adr/0034-project-and-its-files.md)). The digests let the files deposited
later be shown to be the files described.

```console
$ uv run dd-inventory path/to/dataset -o inventory.json
```

Hidden files and folders (names beginning with `.`) are skipped, symbolic links are not
followed, and both are counted in `inventory_limitations`. If fido cannot be loaded, formats are
guessed from file extensions and the inventory says so.

The package does not depend on the contract or any other part of Data Director
([ADR-0031](../docs/adr/0031-ecosystem-and-repository-boundaries.md) decision 7). Its tests check
what it writes against the contract's `FileInventory` schema.

| Module | What it does |
|---|---|
| `scan.py` | Walks the folder, digests each file and assembles the inventory. |
| `identify.py` | The one module that calls fido, with the extension fallback. |
| `tables.py` | Infers a table's fields with Frictionless. |
| `cli.py` | The `dd-inventory` command. |
