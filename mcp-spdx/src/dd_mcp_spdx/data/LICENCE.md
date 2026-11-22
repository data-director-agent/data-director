# Licence for the SPDX licence list records

`licenses-*.jsonl` is derived from the [SPDX License List](https://spdx.org/licenses/), as
published in [`spdx/license-list-data`](https://github.com/spdx/license-list-data): one line per
licence of the release named in `manifest.json`, keeping each licence's identifier, name, SPDX
page, OSI and FSF flags, whether its identifier is deprecated, and the URLs SPDX lists for its
text. `manifest.json` records the release, the file it was derived from and the SHA-256 of each.

The SPDX License List data are released under
[CC0-1.0](https://creativecommons.org/publicdomain/zero/1.0/) by the Linux Foundation and the SPDX
project. These files are therefore available under CC0-1.0, separately from the MIT licence that
covers the code of this package. Source: SPDX License List, spdx/license-list-data.

`scripts/pin_spdx_list.py` in the source repository rebuilds them for a new release.
