# dd-metadata-records

Metadata records in any standard. It holds three things:

- codecs, which parse a serialisation into a generic tree and write a tree back to it;
- standards' definitions, which say how a standard's logical model is written and which existing
  term each property means;
- the pivot, the graph of those terms that a record in any standard is read as.

The design is in [Metadata standards](../docs/specs/metadata-standards.md).

```python
>>> from dd_metadata_records import discover
>>> datacite = discover().covering("http://datacite.org/schema/kernel-4", "application/json")
>>> record = datacite.read('{"titles": [{"title": "Soil cores"}]}', "application/json")
>>> record.values("titles")
['Soil cores']
>>> record.pivot().values_of("http://schema.org/name")
['Soil cores']
```

It is contract-free. It imports no other Data Director package, and its one dependency is PyYAML,
so it can be copied out and published on its own
([System and boundaries](../docs/specs/system.md)). In Data Director, the harness reads an
approved record through it to validate, package and deposit it, and the Metadata Librarian, the
Documentation Editor and the FAIR Assessor read records through it. No module outside a
definition names one of its standard's properties (`scripts/check_standard_keys.py`).

## Codecs

A codec is identified by an identifier that names one byte output for good. The same tree always
writes to the same text, so the digest of a record recorded at approval is the digest of what is
deposited. A codec refuses text over `MAX_RECORD_BYTES` before parsing it.

| Identifier | Media type | Output |
|---|---|---|
| `json-indent-2` | `application/json` | UTF-8, two spaces of indentation, keys in the tree's order, characters outside ASCII as they are, and a final newline |
| `xml-indent-2` | `application/xml` | UTF-8 with a declaration, the root's namespaces declared on it in order of prefix, two spaces of indentation, an element with nothing in it written empty, and a final newline. It refuses a document type or entity declaration, so it resolves no external entity and fetches nothing. Standard library only |

## Standards

A definition is a YAML file. It gives:

- the `conforms_to` URIs it covers;
- its serialisations, each with its codec, the envelopes a record may be wrapped in, and how a gap
  is written;
- its properties, by their path in the standard's logical model.

For each property it gives the key that holds the value in each entry, the pivot `term`, a
`qualified` term for entries whose qualifier matches, and the terms of an entry's `parts`. A
record is read and written as a logical tree in which a gap is `None`, and each serialisation
writes a gap its own way, so a gap is never taken for a value. A definition may also carry a
`drafting` block: what to ask for a gap, what a person must decide may be published before the
value is asked, what a model may suggest, and what is filled by rule. That block is advice to a
drafter and a ceiling, not a licence.

| Identifier | Standard | Serialisations | Mapping |
|---|---|---|---|
| `datacite-4` | [DataCite Metadata Schema 4](https://schema.datacite.org/meta/kernel-4/) | JSON, the form of the DataCite REST API's attributes | [DataCite's mapping to schema.org](https://github.com/datacite/schema.org) |
| `dublin-core-oai` | [Dublin Core Metadata Element Set 1.1](https://www.dublincore.org/specifications/dublin-core/dces/), the 15 elements as OAI-DC carries them | OAI-DC XML, each gap written as `:unav` | The terms DataCite's definition gives the property of the same meaning, after [DataCite's mapping to Dublin Core](https://datacite-metadata-schema.readthedocs.io/en/4.5/mappings/dublincore/) |

For an XML serialisation, the definition also gives its layout (`xml`): the root element, the
namespaces declared on it, the schema it names, and the element each property is written as. The
codec reads and writes elements and knows no standard; the layout makes a document the standard's
logical tree.

A property holds a list of values if its entries have a value key, or if the definition marks it
`repeats: true`; `properties_repeat: true` at the top of a definition marks every property so, as
Dublin Core's elements are.

## Converting

`convert(record, target)` writes a record as a logical tree of another standard, through the pivot,
and invents nothing:

```python
>>> from dd_metadata_records import convert, discover
>>> found = discover()
>>> datacite = found.covering("http://datacite.org/schema/kernel-4", "application/json")
>>> dc = found.by_uri("http://www.openarchives.org/OAI/2.0/oai_dc/")
>>> record = datacite.read('{"titles": [{"title": "Soil cores"}], "publicationYear": "2026"}', "application/json")
>>> conversion = convert(record, dc.definition)
>>> conversion.tree
{'title': ['Soil cores']}
>>> conversion.unplaced
('publicationYear',)
```

Each value is written into the target property read under the same term, or under a qualified
term, with the qualifier that term's rule names. The result says what it could not place
(`unplaced`, by path in the source) and what it placed less precisely (`reduced`): a structured
value whose parts the target has no place for, or a second value where the target holds one. A
gap is not copied, and a property with no value in the source is left out; whether that is
acceptable is for the target's requirements to say.

A definition says nothing about what a repository requires. That is a requirement set's job.

## Registering

Codecs and standards are found by entry point. A codec goes in the `dd_metadata_records.codecs`
group, named by its identifier. A definition goes in the `dd_metadata_records.standards` group,
named by its standard's identifier, as a `Definition` loaded with `dd_metadata_records.load`.
`discover()` refuses:

- a definition that names a codec nobody registered;
- two definitions that cover the same `conforms_to` URI.

## Honest limits

- There are two standards, each in one serialisation. UK GEMINI is TODO(#1361).
- An XML layout writes each property as repeatable text elements under the root. A property under
  nested elements, as ISO 19139 has, is TODO(#1361). Attributes such as `xml:lang` are read but
  not mapped to the pivot.
- A conversion copies only what has a pivot term in both standards. A controlled value, such as
  DataCite's `resourceTypeGeneral` or a DCMI Type, is copied as it is, not mapped to the target's
  vocabulary.
- A definition covers the properties a drafter writes or a reader reads, not every property of
  its standard. A property it does not name is listed as unmapped, and is never dropped
  silently.
- A definition's version is raised by hand on every change. Nothing checks that it was.

## Credit

The DataCite terms follow DataCite's own [mapping to schema.org](https://github.com/datacite/schema.org)
where it gives one. The pivot terms are those of [schema.org](https://schema.org/),
[DCMI Metadata Terms](https://www.dublincore.org/specifications/dublin-core/dcmi-terms/),
[DCAT](https://www.w3.org/TR/vocab-dcat-3/) and [PROV-O](https://www.w3.org/TR/prov-o/).

The Dublin Core elements are those of the
[Dublin Core™ Metadata Element Set, version 1.1](https://www.dublincore.org/specifications/dublin-core/dces/),
as the [OAI-PMH](https://www.openarchives.org/OAI/openarchivesprotocol.html#dublincore) carries
them. The tests validate a drafted OAI-DC record against the OAI-DC XML Schema and the two schemas
it imports. These are copied unchanged into `tests/data/xsd/`, and each stays under its
publisher's licence (the Open Archives Initiative's, DCMI's and W3C's), as
[`tests/data/xsd/NOTICE.md`](tests/data/xsd/NOTICE.md) says. They are test data and are not in the
library's wheel. The tests use [lxml](https://lxml.de/) to validate; the library itself does not.
