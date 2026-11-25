# dd-duo

Data use conditions from the [GA4GH Data Use Ontology](https://github.com/EBISPOT/DUO) (DUO).
DUO gives standard terms for the conditions under which data may be used, as consent forms and
data access committees state them. A **permission** says what use is allowed (general research
use, health or medical research). A **modifier** adds a condition to it (ethics approval
required, non-commercial use only, publication required). Each term has an identifier, such as
`DUO:0000021`, and most have a shorthand, such as `IRB`. This library gives the terms of a pinned
DUO release, held as data, so naming a condition needs no network and sends nothing anywhere.

```python
>>> from dd_duo import lookup, release, terms
>>> lookup("IRB")
Term(id='DUO:0000021', shorthand='IRB', label='ethics approval required', definition='This data use modifier indicates that the requestor must provide documentation of local IRB/ERB approval.', kind='modifier', parent=None, url='http://purl.obolibrary.org/obo/DUO_0000021')
>>> [t.shorthand for t in terms("permission")]
['NRES', 'HMB', 'DS', 'POA', 'GRU']
>>> release().version
'2021-02-23'
```

`lookup` takes an identifier or a shorthand, ignoring case, and gives None for a name the pinned
release has no current term for. `terms()` gives every current term in identifier order, or those
of one kind. `release()` says which release the terms come from, and gives the SHA-256 of the
terms file. The loader refuses data that do not match it.

The library is contract-free: it imports no other Data Director package and nothing outside the
standard library, so it can be copied out and published on its own
([System and boundaries](../docs/specs/system.md)). The Research Ethics Adviser
(`advisor.ethics`) uses it to name the data use conditions that a researcher should check
participants' consent against. The same codes are meant for the access options of the rights
adviser (TODO(#359)).

## Sources and licences

The code is under the MIT licence (`LICENSE`). The terms in `src/dd_duo/data/` are derived from
the GA4GH Data Use Ontology release `v2021-02-23`, the latest release, under the
[Creative Commons Attribution 4.0 International licence](https://creativecommons.org/licenses/by/4.0/)
(`src/dd_duo/data/LICENCE.md`). Source: GA4GH Data Use Ontology, developed by the Global
Alliance for Genomics and Health and maintained at EMBL-EBI.

## Updating to a new release

`scripts/pin_duo.py` builds the terms from the `duo.owl` of a tagged release:

```bash
curl -sfLO https://raw.githubusercontent.com/EBISPOT/DUO/v2021-02-23/duo.owl
```

```bash
uv run --no-project --python 3.14 duo/scripts/pin_duo.py duo.owl --version 2021-02-23
```

Then update the copy that each deployment pins for the source check (`app/config/sources.yaml`,
`workbench/sources.yaml`) with the new file's label and SHA-256.

## Honest limits

- It covers permissions and modifiers only. It leaves out the two root classes, obsolete terms
  (such as `RU` and `GRU-CC`, which a consent record may still carry) and DUO's research-type
  classes, which are neither.
- It does not cover restrictions that need a second ontology, such as the disease of `DS` or the
  region of `GS`. The term names the kind of condition; the value is not modelled.
- It gives the terms only. It does not say which conditions apply to a dataset: that is what a
  consent form and the people who approved it say.

## Dependencies

None beyond Python 3.14's standard library.
