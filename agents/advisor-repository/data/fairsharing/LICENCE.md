# Licence for `snapshot.jsonl`

The records in `snapshot.jsonl` are taken from FAIRsharing's database records on
[FAIRsharing](https://fairsharing.org). They were fetched through the public record route named
in `manifest.json` on the date it records.

FAIRsharing content is licensed under the
[Creative Commons Attribution-ShareAlike 4.0 International licence (CC BY-SA 4.0)](https://creativecommons.org/licenses/by-sa/4.0/).
This file, `snapshot.jsonl` and `manifest.json` are therefore themselves available under
CC BY-SA 4.0, separately from the MIT licence that covers the code in this repository.

Attribution, as FAIRsharing requests in its API responses: please link to
<https://fairsharing.org> and use the attribution badge at
<https://api.fairsharing.org/img/fairsharing-attribution.svg>.

Each record carries its FAIRsharing DOI, so any candidate the agent offers attributes its source.
Only the fields read in `src/dd_agent_advisor_repository/records.py` are kept; contact details and other
personal data in the full records are not copied.
