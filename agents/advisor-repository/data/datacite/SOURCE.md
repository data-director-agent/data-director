# Source of the DataCite repositories snapshot

The repository advisor reads the repositories DataCite registers that re3data does not list, such
as many universities' own data repositories, from `repositories.jsonl`. `manifest.json` pins it:

- `fetched_at`: when it was fetched from DataCite's REST API (`source`);
- `records` and `sha256`: how many repositories it holds, and the SHA-256 of the file.

`uv run dd-datacite fetch` fetches it anew (`src/dd_agent_advisor_repository/datacite.py`). It keeps a
repository when DataCite marks it active, as a repository, it links to no re3data record (re3data
describes those, with more facts), and it has registered at least one DOI of resource type
Dataset. The snapshot is committed, as the FAIRsharing snapshot is: DataCite publishes no archive
that could be fetched again to the same bytes. After fetching, update both `sources.yaml` pins
(`app/config/sources.yaml`, `workbench/sources.yaml`) with the new `snapshot_ref` and `sha256`.

## What each record holds

From the repository: its DataCite identifier, name, alternate name, URL, repository types,
software, certificates, OpenDOAR identifier, DOI prefixes, and how many Dataset DOIs it has
registered. From its DataCite member, or consortium organisation: its name, ROR identifier,
country (ISO 3166-1 alpha-2) and organisation type. Descriptions and contact details are not kept.

## Citation

> DataCite REST API, repositories and providers. https://support.datacite.org/docs/api
> (fetched on the date in `manifest.json`).

## Licence and use

DataCite makes its metadata available under
[CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/), so the snapshot carries no
conditions. We credit DataCite nonetheless, in every statement the advisor makes from these
records. A run never asks DataCite (Blueprint P14); the snapshot is fetched once per refresh,
with a `User-Agent` that names the project, not a person.
