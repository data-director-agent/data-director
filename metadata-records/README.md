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

## Standards

A definition is a YAML file. It gives:

- the `conforms_to` URIs it covers;
- its serialisations, each with its codec, the envelopes a record may be wrapped in, and how a gap
  is written;
- its properties, by their path in the standard's logical model.

For each property it gives the key that holds the value in each entry, the pivot `term`, a
`qualified` term for entries whose qualifier matches, and the terms of an entry's `parts`. It may
also carry a `drafting` block: what to ask for a gap, what a person must decide may be published
before the value is asked, what a model may suggest, and what is filled by rule. That block is
advice to a drafter and a ceiling, not a licence.

| Identifier | Standard | Serialisations | Mapping |
|---|---|---|---|
| `datacite-4` | [DataCite Metadata Schema 4](https://schema.datacite.org/meta/kernel-4/) | JSON, the form of the DataCite REST API's attributes | [DataCite's mapping to schema.org](https://github.com/datacite/schema.org) |

A definition says nothing about what a repository requires. That is a requirement set's job.

## Registering

Codecs and standards are found by entry point. A codec goes in the `dd_metadata_records.codecs`
group, named by its identifier. A definition goes in the `dd_metadata_records.standards` group,
named by its standard's identifier, as a `Definition` loaded with `dd_metadata_records.load`.
`discover()` refuses:

- a definition that names a codec nobody registered;
- two definitions that cover the same `conforms_to` URI.

## Honest limits

- There is one standard and one serialisation. Dublin Core in XML is TODO(#1360), and UK GEMINI is
  TODO(#1361).
- The pivot is read from a record, but no record is written from it yet: a conversion between
  standards is TODO(#1363).
- A definition covers the properties a drafter writes or a reader reads, not every property of
  its standard. A property it does not name is listed as unmapped, and is never dropped
  silently.
- A definition's version is raised by hand on every change. Nothing checks that it was.

## Credit

The DataCite terms follow DataCite's own [mapping to schema.org](https://github.com/datacite/schema.org)
where it gives one. The pivot terms are those of [schema.org](https://schema.org/),
[DCMI Metadata Terms](https://www.dublincore.org/specifications/dublin-core/dcmi-terms/),
[DCAT](https://www.w3.org/TR/vocab-dcat-3/) and [PROV-O](https://www.w3.org/TR/prov-o/).
