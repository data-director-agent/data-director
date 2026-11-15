# Source of the ROR registry

The policy advisor identifies a funder in the [Research Organization Registry](https://ror.org)
(ROR) before it searches FAIRsharing for the funder's policy. It reads ROR from one of its data
dumps, which `manifest.json` pins:

- `archive` and `archive_sha256`: the dump as ROR publishes it on Zenodo, a zip holding one JSON
  file of every organisation in ROR schema v2 (and a CSV, which is not read);
- `version`, `doi` and `fetched_at`: which dump, its own DOI, and when it was pinned;
- `snapshot_sha256`: `registry.jsonl`, built from the archive by `uv run dd-sources prepare`
  (or `uv run dd-ror fetch`, which builds this registry alone).

Neither the archive nor `registry.jsonl` is committed. Building downloads the pinned archive once
on each machine, keeps it in `archives/` (or the cache it is given), checks it against the pin and
builds the registry from it. The registry is the same bytes on every machine, so the harness
checks ROR evidence against it. `uv run dd-ror fetch --update-pin` pins the newest dump; update
the pin in both `sources.yaml` files with it.

## Citation

Cite the dump as ROR asks, with the version in `manifest.json`:

> Research Organization Registry (ROR) data dump. https://doi.org/10.5281/zenodo.6347574

Each organisation has its own identifier, `https://ror.org/<id>`, and the advisor cites it by
that identifier in its evidence.

## Licence and use

ROR releases its data under [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/), so the
registry carries no conditions. We attribute ROR nonetheless: in `CITATION.cff`, in the README,
and in the advisor's statement, which names the copy of ROR that answered.

- **Fields.** Only the fields of `Organisation` in `src/dd_agent_advisor_policy/ror.py` are
  kept: the identifier, names with their types and languages, the kinds of organisation, status,
  country codes, Crossref Funder IDs and parent organisations. Links, domains, coordinates and
  ROR's administrative dates are dropped.
- **Load on ROR.** The dump is downloaded once per pin by each machine, from Zenodo. A run never
  downloads it. The live route (`DD_POLICY_ROR=live`) asks `api.ror.org` once for each funder,
  and is off by default.
- **User-Agent.** Downloads and live requests name the project and its repository, not a person.
