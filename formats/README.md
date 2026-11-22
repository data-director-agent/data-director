# dd-formats

File formats described from their [PRONOM](https://www.nationalarchives.gov.uk/PRONOM/) records.
PRONOM, the technical registry of The National Archives, gives each file format an identifier (a
PUID, such as `fmt/353`) and a record of its name, version, media types and file extensions.
Format identification tools such as DROID, fido and Siegfried report PUIDs; this library turns one
into its record, from a pinned PRONOM release held as data, so naming a format needs no network
and sends nothing anywhere.

```python
>>> from dd_formats import lookup, release
>>> lookup("fmt/353")
FormatRecord(puid='fmt/353', name='Tagged Image File Format', version=None, media_types=('image/tiff',), extensions=('tif', 'tiff'), superseded_by=None, url='https://www.nationalarchives.gov.uk/PRONOM/fmt/353')
>>> lookup("fmt/10").puid  # deprecated in favour of fmt/353
'fmt/353'
>>> release().version
125
```

`lookup` gives None for a PUID the pinned release does not have, and follows a deprecated PUID to
the one that replaces it where PRONOM names one. `release()` says which release the records come
from and the SHA-256 of the records file; the loader refuses data that do not match it.

It is contract-free: it imports no other Data Director package and nothing outside the standard
library, so it can be copied out and published on its own
([System and boundaries](../docs/specs/system.md)). The File Archivist (`advisor.files`) uses it
to name each file's format from the PUIDs `dd-inventory` recorded, and cites the record it used.

## Sources and licences

The code is under the MIT licence (`LICENSE`). The records in `src/dd_formats/data/` are derived
from PRONOM release v125 (2 September 2026), © Crown copyright, The National Archives, under the
[Open Government Licence v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/)
(`src/dd_formats/data/LICENCE.md`). Source: The National Archives, PRONOM.

## Updating to a new release

`scripts/pin_pronom_records.py` builds the records from a fido format file of one release, the
one `dd-inventory` identifies against (`inventory/scripts/pin_pronom.py`), so the two stay on the
same release:

```bash
uv run --no-project --python 3.14 formats/scripts/pin_pronom_records.py inventory/src/dd_inventory/pronom/formats-v125.xml.gz --version 125 --release-created 2026-09-02
```

Then update the copy each deployment pins for the source check (`app/config/sources.yaml`,
`workbench/sources.yaml`) with the new file's label and SHA-256.

## Honest limits

- Names, versions, media types and extensions only: PRONOM's descriptions, signatures and
  relationships between formats are left out.
- PRONOM says nothing about whether a format is open or suited to preservation; that is for the
  caller to judge.
- The records are those of the pinned release; a format added since is not known until the next
  pin.

## Dependencies

None beyond Python 3.14's standard library.
