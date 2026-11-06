# Source of the re3data registry

The repository advisor reads every repository in
[re3data.org](https://www.re3data.org), the Registry of Research Data Repositories, from one of
its monthly exports. `manifest.json` pins it:

- `archive` and `archive_sha256`: the export as re3data publishes it
  (<https://www.re3data.org/data>), one XML file per repository;
- `month` and `fetched_at`: which export, and when it was pinned;
- `snapshot_sha256`: `registry.jsonl`, built from the archive by `uv run dd-re3data fetch`.

Neither the archive nor `registry.jsonl` is committed. `fetch` downloads the pinned archive once,
keeps it in `archives/`, checks it against the pin and builds the registry from it. The registry
is the same bytes on every machine, so the harness checks re3data evidence against it.

## Citation

Cite the service as re3data asks:

> re3data.org - Registry of Research Data Repositories. https://doi.org/10.17616/R3D
> (export of the month in `manifest.json`).

The records follow the re3data.org Metadata Schema for the Description of Research Data
Repositories, version 4.0 (https://doi.org/10.48440/re3.014). Each record has its own DOI under
10.17616, and the advisor cites a repository by that DOI in its evidence.

## Licence and use

re3data publishes its database entries under
[CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/), so the registry carries no
conditions. We attribute re3data nonetheless: in `CITATION.cff`, in the README, and in every
statement the advisor makes from these records.

- **Fields.** Only the fields read in `src/dd_agent_advisor_repository/records.py` are kept.
  Contact details are dropped.
- **Load on re3data.** It is asked once per pin by each machine, and the monthly refresh moves the
  pin. A run never asks re3data (Blueprint P14).
- **User-Agent.** Downloads name the project and its repository, not a person.
- **No logos.** re3data's logo and branding are not used.
- **Errors.** When we find a record wrong, we report it to re3data rather than only correcting it
  locally: TODO(#488).
