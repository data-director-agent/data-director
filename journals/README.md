# dd-journals

Journals by ISSN and title, for a form that asks which journal someone plans to publish in.

The [ISSN International Centre](https://www.issn.org) assigns each journal its ISSNs, one for
each medium (print, online), and a linking ISSN (ISSN-L) that groups them. Its register, the
[ISSN Portal](https://portal.issn.org), is the authoritative reference, but its API and bulk
data need a subscription. [OpenAlex](https://openalex.org) publishes, under CC0, about 170,000
journals with their ISSN-L, other ISSNs, publisher, country and open access status, built partly
from the ISSN-L data. This library builds a registry of those journals from one pinned OpenAlex
snapshot and looks journals up in it, so a look-up needs no network and sends nothing anywhere.
Each journal links to its ISSN Portal record.

```python
>>> from dd_journals import registry
>>> journals = registry()
>>> journals.get("1879-1026")  # any ISSN: print, online or linking
Journal(issn_l='0048-9697', issns=('0048-9697', '1879-1026'), title='Science of The Total Environment', ...)
>>> [j.title for j in journals.search("total environment", limit=3)]
['Science of The Total Environment', ...]
>>> journals.get("0048-9697").portal_url
'https://portal.issn.org/resource/ISSN/0048-9697'
```

- `get(issn)` finds the journal by any of its ISSNs, or gives None.
- `search(text, limit=10)` takes what a person typed. If it is an ISSN, the answer is that
  journal. Otherwise journals are matched on their title, alternate titles and abbreviated
  title, with case, accents, punctuation and a leading "The" set aside and "&" read as "and":
  1. a title the same as the text;
  2. then a title starting with it;
  3. then one in which every word typed starts a word.

  Within each group, journals with more works come first, then by ISSN-L, so the same text always
  gives the same list.
- `normal_issn(value)` writes an ISSN as `NNNN-NNNC`. `valid_issn(value)` also checks its check
  digit.
- `Registry(journals)` and `Registry.load(path, sha256)` build a registry from other journals or
  another file.

It is contract-free: it imports no other Data Director package and needs only the standard
library, so it can be copied out and published on its own
([System and boundaries](../docs/specs/system.md)). The policy advisor (`advisor.policy`) uses
its ISSN functions. Journal look-up for agents and the app's journal picker are to follow (#1514).

## Building the registry

The registry is not committed: it holds about 170,000 journals in 63 MB. `src/dd_journals/data/manifest.json` pins one
quarterly OpenAlex snapshot. It records each part of the snapshot's Sources entity by URL, size
and SHA-256, and the SHA-256 of the `journals.jsonl` they build. OpenAlex's own manifest gives no
hashes, so the hashes are taken when the snapshot is pinned.

```bash
uv run dd-journals fetch
```

This downloads the pinned parts (about 364 MB, gzipped) from OpenAlex's public bucket into
`src/dd_journals/data/archives/`, or the directory given as `--cache-dir`. It checks each part,
builds `journals.jsonl` and checks that too. A second run downloads nothing.
`uv run dd-journals check` says whether the registry is built as pinned.

The build keeps journals with an ISSN-L only. Where OpenAlex has two records for one ISSN-L, they
become one journal: the record with more works describes it, and it carries the ISSNs of both.
Lines have sorted keys and are sorted by ISSN-L, so the same snapshot always builds the same
bytes.

### Pinning a new snapshot

OpenAlex publishes a snapshot each quarter
([release notes](https://openalex.s3.amazonaws.com/RELEASE_NOTES.txt)).

```bash
uv run dd-journals fetch --update-pin
```

This reads OpenAlex's newest manifest, downloads and hashes every Sources part, builds the
registry and rewrites `manifest.json`. Commit the manifest.

## Sources and licences

The code is under the MIT licence (`LICENSE`). The registry is derived from the
[OpenAlex snapshot](https://help.openalex.org/access/snapshot/), released under
[CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/) (`src/dd_journals/data/SOURCE.md`).
OpenAlex asks to be cited as:

> Priem, J., Piwowar, H., & Orr, R. (2022). OpenAlex: A fully-open index of scholarly works,
> authors, venues, institutions, and concepts. https://doi.org/10.48550/arXiv.2205.01833

The ISSN Portal links point to the ISSN International Centre's register. Nothing is copied from
it. Whether the Centre's ISSN-L table may be pinned too, to check OpenAlex's links between ISSNs,
is TODO(#1515).

## Honest limits

- OpenAlex is not the ISSN register. Its title is OpenAlex's display name, which can differ from
  the ISSN key title. A journal OpenAlex does not list, or lists without an ISSN-L, is not found.
- The registry is that of the pinned snapshot. A journal added since is not known until the next
  pin.
- "Publisher" is OpenAlex's host organisation, which is sometimes a society or a platform rather
  than the publisher.
- Search reads every journal, about 150 ms a query; loading the registry takes a few seconds.
  A caller that answers a person as they type should load it once and pause typing first.
- Search matches words, not meaning. A misspelt title finds nothing; use the ISSN.

## Dependencies

None beyond Python 3.14's standard library. Building the registry needs HTTPS access to
`openalex.s3.amazonaws.com`.
