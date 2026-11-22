# Licence for the PRONOM records

`pronom-v*.jsonl` is derived from [PRONOM](https://www.nationalarchives.gov.uk/PRONOM/), the
technical registry of The National Archives: one line per format record of the release named in
`manifest.json`, keeping the format's PUID, name, version, media types and file extensions, and
the PUID that replaces a deprecated one. `manifest.json` records the release, the file it was
derived from and the SHA-256 of each.

Contains public sector information licensed under the
[Open Government Licence v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/).
These files are therefore available under the Open Government Licence v3.0, separately from the
MIT licence that covers the code of this package. Source: The National Archives, PRONOM.

`scripts/pin_pronom_records.py` in the source repository rebuilds them for a new release.
