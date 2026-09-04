# Licence for `snapshot.jsonl`

The records in `snapshot.jsonl` are a projection of metadata records from
[FAIRsharing](https://fairsharing.org), fetched through the public record route named in
`manifest.json` on the date it records.

FAIRsharing content is licensed under the
[Creative Commons Attribution-ShareAlike 4.0 International licence (CC BY-SA 4.0)](https://creativecommons.org/licenses/by-sa/4.0/).
This file, `snapshot.jsonl` and `manifest.json` are therefore themselves available under
CC BY-SA 4.0, separately from the MIT licence that covers the code in this repository.

Attribution, as FAIRsharing requests in its API responses: please link to
<https://fairsharing.org> and use the attribution badge at
<https://api.fairsharing.org/img/fairsharing-attribution.svg>.

Each record carries its FAIRsharing DOI and URL, so any recommendation the workbench produces
attributes its source. Only the fields listed in `agents/r3/fairsharing/records.py` are kept;
contact details and other personal data present in the full records are not copied.

To rebuild the snapshot: `uv run python scripts/build_snapshot.py` (no account required).
