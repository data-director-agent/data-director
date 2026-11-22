# Licence for the PRONOM signatures

The files in this folder other than this one are taken or derived from
[PRONOM](https://www.nationalarchives.gov.uk/PRONOM/), the technical registry of The National
Archives:

- `container-signature-*.xml` is PRONOM's container signature file, unmodified.
- `formats-v*.xml.gz` is a fido format file converted from PRONOM's format records by fido's own
  converter (`fido.prepare`), listing the formats of the release named in `manifest.json`.
- `manifest.json` records where each came from, when, and its SHA-256.

Contains public sector information licensed under the
[Open Government Licence v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/).
These files are therefore available under the Open Government Licence v3.0, separately from the
MIT licence that covers the code in this repository. Source: The National Archives, PRONOM.

`inventory/scripts/pin_pronom.py` in the source repository rebuilds them for a new release.
