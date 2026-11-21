# dd-units

Turns a unit as a person writes it into a [UCUM](https://ucum.org/) code, by rule:
"micrometres" and "µm" become `um`, "°C" and "degC" become `Cel`, "mg per litre" becomes `mg/L`
and "kg m-3" becomes `kg.m-3`. A data dictionary can then say what unit a field is in, in a form a machine
can read and convert.

```python
>>> from dd_units import ucum_code
>>> ucum_code("micrometres")
UcumUnit(code='um', name='micrometre', matched_by='name')
>>> ucum_code("C") is None   # the coulomb in UCUM, but usually meant as a degree Celsius
True
```

It is contract-free: it imports no other Data Director package, so it can be copied out and
published on its own ([System and boundaries](../docs/specs/system.md)). The Documentation Editor
uses it to fill a data dictionary's `unit_code` column
([Drafting documents](../docs/specs/drafting.md)).

## How a unit is matched

In order, and never by guessing:

1. **The whole phrase**, as a UCUM unit name ("degree Celsius"), a print symbol ("°C") or one of
   a few common spellings UCUM does not list (`ALIASES`: "degC", "micron", "hrs", "percent").
2. **Term by term.** The text is split at "/", "per", "." and spaces. Each term is a unit atom,
   with an optional prefix and exponent, found by its UCUM code, name or print symbol. British
   spellings and plurals are accepted ("micrometres", "litres"), as are "µ", superscripts ("m²"),
   "^" and words for powers ("square metres", "metres cubed").
3. **As written**, if it is already a valid UCUM expression ("10*3/uL", "{cells}/mL").

Every code returned is checked against the UCUM grammar. Where UCUM gives one name or symbol to
several units, the most general class wins. SI and ISO 1000 come first, then the international
customary units, then avoirdupois weights. So "foot" is `[ft_i]` and "pound" is `[lb_av]`. Where
two units remain, as for "pint" or "gallon" (US or British), the name matches nothing. Codes whose
everyday reading differs from UCUM's (`AMBIGUOUS`: `C`, `F`, `G`, `B`, `b`, `deg`) match nothing
when written alone, so that a person is asked. With a prefix (`mC`), they mean what UCUM says.

`means_no_unit` says whether the text means the field has no unit ("none", "n/a",
"dimensionless").

## Honest limits

- It recognises units, not quantities: "m" is a metre, whatever the field measures.
- It does not convert values, and does not choose between equivalent codes: `kg/m3` and
  `kg.m-3` are both returned as written or composed.
- Arbitrary units and annotations (`[IU]`, `{cells}`) are matched only when written as UCUM
  writes them.
- Names are UCUM's (`ucum_version()`), in British spelling.

## Dependencies

[ucumvert](https://github.com/dalito/ucumvert) (MIT), which implements the UCUM grammar with
[lark](https://github.com/lark-parser/lark) and ships `ucum-essence.xml`, the UCUM table this
library reads its names, symbols and prefixes from. The table is under the
[UCUM Copyright Notice and License](https://github.com/ucum-org/ucum/blob/main/LICENSE.md).
ucumvert also brings [pint](https://github.com/hgrecco/pint), which this library does not use.
Only `dd_units._ucum` imports ucumvert ([Dependencies](../docs/specs/dependencies.md)).

## Licence

MIT.
