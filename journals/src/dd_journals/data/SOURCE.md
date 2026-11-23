# Source of the journal registry

`journals.jsonl` is built from the Sources entity of one [OpenAlex](https://openalex.org)
snapshot, which `manifest.json` pins:

- `snapshot_date`: the release, as OpenAlex dates it;
- `snapshot_manifest`: OpenAlex's manifest of that release;
- `parts`: each gzipped JSON Lines part of the Sources entity, by URL, size, record count and the
  SHA-256 taken when it was pinned;
- `journals` and `registry_sha256`: how many journals the parts build, and the SHA-256 of
  `journals.jsonl`;
- `fetched_at`: when the snapshot was pinned.

Neither the parts nor `journals.jsonl` is committed. `uv run dd-journals fetch` downloads the
pinned parts once on each machine and keeps them in `archives/`. It checks each part against its
pin, builds the registry and checks the registry too. The registry is the same bytes on every
machine. `uv run dd-journals fetch --update-pin` pins the newest snapshot.

Each line keeps, for one journal: its ISSN-L, its ISSNs, title, alternate and abbreviated
titles, host organisation (publisher), country, homepage, its DOAJ and open access flags, its
OpenAlex identifier and its count of works.

## Citation

> Priem, J., Piwowar, H., & Orr, R. (2022). OpenAlex: A fully-open index of scholarly works,
> authors, venues, institutions, and concepts. https://doi.org/10.48550/arXiv.2205.01833

## Licence and use

OpenAlex releases its data under [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/)
(`LICENCE.md`), so the registry may be copied, changed and redistributed without permission.
Citing OpenAlex is asked, not required.
