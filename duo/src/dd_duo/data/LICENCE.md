# Licence for the DUO terms

`duo-*.jsonl` is derived from the [GA4GH Data Use Ontology](https://github.com/EBISPOT/DUO)
(DUO), developed by the Global Alliance for Genomics and Health and maintained at EMBL-EBI: one
line per current data use permission or modifier of the release named in `manifest.json`,
keeping the term's identifier, shorthand, label, definition, kind and parent. `manifest.json`
records the release, the file it was derived from and the SHA-256 of each.

DUO is available under the
[Creative Commons Attribution 4.0 International licence](https://creativecommons.org/licenses/by/4.0/)
(CC BY 4.0), and so are these files, separately from the MIT licence that covers the code of this
package. Source: GA4GH Data Use Ontology, https://github.com/EBISPOT/DUO. The records are
reduced from the release's `duo.owl`; nothing in them is otherwise changed.

`scripts/pin_duo.py` in the source repository rebuilds them for a new release.
