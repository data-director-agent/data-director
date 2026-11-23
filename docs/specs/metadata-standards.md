# Metadata standards

## Intent and scope

Most projects reach Data Director with no metadata record a repository would accept, so the Metadata
Librarian drafts one ([Drafting documents](drafting.md)). A repository expects its own standard:
re3data lists Dublin Core for 17 repositories and DataCite for 13, the NERC EDS centres expect UK
GEMINI on ISO 19115, and social science archives expect DDI. The Librarian must be able to draft in
whichever standard the chosen repository's requirements follow, without a new drafter for each, and
without any one standard becoming the format of the tool.

This spec says what a metadata standard is to Data Director, where each part of it lives, how a
record is written, read and checked in any standard, and how a record is carried from one standard
to another. It does not cover what a repository asks beyond its standard, which is a requirement set
([Deposit](deposit.md)); what a drafter may infer, ask and write ([Drafting documents](drafting.md));
or how a record reaches a repository ([Deposit](deposit.md), *Packagers and transports*).

It does not cover reading a record a researcher already has, or extracting metadata from data files
(#789). The design leaves room for both: a standard's definition is the place to say how a record in
it is recognised, and the codecs are shared. Neither is built or specified here.

**What is built.** The metadata record is DataCite in its JSON form, and DataCite's keys are written
into the Librarian (`datacite.yaml`), the deposit check (`VALUE_KEYS`), the Documentation Editor's
reader and the Zenodo item. A requirement set names a schema.org term for each field, and validation
reads a record as RDF through it. Everything below is the design that replaces those; each part names
the issue that builds it. Until then the code does what *What is built* says, and a statement here
that the code does not yet meet is marked in place.

## Invariants

1. **A record is in one standard and one serialisation, and says which.** A metadata record is a
   `Document` of kind `metadata_record` whose `conforms_to` names its standard and whose
   `media_type` names its serialisation. The harness accepts a record only for a pair that a
   registered standard defines, and refuses any other before it is validated or packaged. TODO(#1358).
2. **The record is the record of truth.** Every other form of its content, the pivot graph, a
   conversion, a platform's item, is derived from it, kept by its digest, never edited and never a
   document ([Deposit](deposit.md), invariant 16). A conversion is never approved in the record's
   place.
3. **A standard is a definition, not code.** Adding a standard adds a definition, and a codec only
   if its serialisation has none. No module outside a standard's own definition names one of its
   properties. A check fails a module that does, as `scripts/check_boundaries.py` fails an
   undeclared import. TODO(#1358).
4. **A codec knows no standard, and writes the same bytes for the same tree.** A codec parses a
   serialisation into a generic tree and writes a tree back to it. Approval, the package and a
   deposit name a record by its digest, so a codec's output is deterministic, and its identifier
   names one serialisation for good: a changed output is a new identifier, as a canonicalisation
   keeps its bytes ([Evidence and grounding](grounding.md)).
5. **A property has one name, the standard's own, in every serialisation.** A standard's property is
   identified by the path the standard uses for it in its logical model, such as DataCite's
   `titles[0].title`, whatever serialisation wrote the record. Requirement sets, the drafter's
   questions and their identifiers use that path, so a question has the same identifier in a JSON
   draft and an XML draft of the same standard.
6. **A placeholder is never a value, in any serialisation.** A drafted record has a gap where the
   researcher must say something ([Drafting documents](drafting.md), invariant 2). Each standard says
   how its serialisations write a gap, and every reader, including the validation, the package and
   the Documentation Editor, takes it as no value.
7. **The pivot uses terms that already exist.** A standard's property maps to a term of an existing
   vocabulary, such as schema.org, Dublin Core Terms, DCAT or PROV-O, named by its IRI, and none is
   invented ([Contract](contract.md), *Vocabularies*). A property with no such term has no pivot
   term: it is not validated through the pivot and a conversion reports it as unplaced.
8. **Two fields of a merged requirement set never share a term**, as before
   ([Deposit](deposit.md), invariant 4), now over the expanded IRI. A standard's definition may map
   two properties to one term, as DataCite's descriptions of different types are, and a set that
   names both is refused on load.
9. **A conversion reports every loss and invents nothing.** Converting a record goes through the
   pivot. It reports each value it could not place and each it placed less precisely, with the
   reason, and a property the target requires that the source cannot supply is a question for the
   researcher, never a value the converter chose. TODO(#1363).
10. **No model writes a mapping, converts a record or writes a value at run time.** A standard's
    definition is a file a person reviews, as a requirement set is, and a drafter follows
    [Drafting documents](drafting.md): it infers only from the project's facts, asks for the rest,
    and a model suggests only beside a question.
11. **A standard is available by being registered.** Standards and codecs are registered by entry
    point, by identifier, as transports are ([Deposit](deposit.md), invariant 17). Unlike a
    transport, a standard sends nothing outside the deployment, so the profile does not choose which
    registered standards are offered. A requirement set that names a standard that is not registered
    stops start-up, as a pair of transport and format the table does not allow does.
12. **A choice records the definition it used.** The project log names the standard's definition by
    `<standard_id>@v<version>` and the SHA-256 of its file, and its codec by identifier, as it names
    each requirement set ([Deposit](deposit.md), invariant 6). A definition's version is raised on
    every change; nothing checks this. TODO(#1358).
13. **A parser reads only the record.** An XML codec resolves no external entity or DTD, fetches
    nothing, and refuses input over a size limit. A record is a few kilobytes, and a parser that
    follows what the document says is a way to read or reach what a researcher did not mean to share.

## Boundaries and contracts

**Three layers.** A record passes through them in this order, and each knows nothing of the one
after it.

1. A **codec** turns a serialisation into a generic tree and back: JSON first, then XML. It is
   identified by its media type and knows no standard.
2. A **standard's definition** says how a standard's logical model is written in each serialisation
   it has, and what each property means in the pivot.
3. The **pivot** is the graph a record is read as, so that a record in any standard can be checked
   and described in the same terms.

**A standard's definition.** One file per standard, shipped with the library that holds the codecs and
versioned by its own `version`. It says:

- which `conforms_to` URIs it covers and which serialisations, each with its codec;
- its properties, by their path in its logical model, and for each one that repeats, the key or
  element that holds its value, which is today `VALUE_KEYS`;
- where each property is in each serialisation;
- the pivot term each property maps to, if it has one, and the source of the mapping, as a set cites
  its guidance (DataCite's published mapping to schema.org, for instance);
- how a gap is written in each serialisation (invariant 6);
- optionally, for a drafter, what to ask about each property, what fills itself by rule, what a
  person must decide may be published before the value is asked, and which properties a model may
  suggest a value for. This is the content of `datacite.yaml`. It is advice to a drafter and a
  ceiling, not a licence: the drafter's own rules in [Drafting documents](drafting.md) still apply.

The definition says nothing about what a repository requires. A definition has no obligation, no
licence list, no form label and no size limit.

**A requirement set** stays as [Deposit](deposit.md) describes it: what a repository requires of a
record in a standard, written in YAML by the people who know the repository. Its fields name
properties of the standard by their path and their qualifier, and their obligation. The term a field
is read under comes from the standard's definition. A field of an override for something the standard
has no property for, such as a Dataverse contact email, names its own term, and a field may not name
a term that differs from the one the standard's definition gives its property. Today a field names a
schema.org term itself and a standard has no definition of its own; the term becomes an IRI in
#1357, and the definition is built in #1358.

A definition and a requirement set have different owners and change at different rates. A definition
describes the format, and changes when the standard does. A set describes a repository's wishes and
changes when it changes its form.

**The pivot.** A record is read as an RDF graph whose subject is the dataset. A property that holds
a value becomes a literal of its term, and a property that holds a structure, such as a creator with
a name, an identifier and an affiliation, becomes a node whose parts have terms of their own, which a
definition lists. The validation counts only that a term has a value, as it does today, and a
conversion uses the parts. Shapes are generated from the merged requirement set's fields, and
pySHACL runs them, as before ([Deposit](deposit.md), *Validation*). The pivot is built for a check or
a conversion and is not kept as a record; the package's root dataset properties are written from it,
as they are from DataCite now.

**Drafting in a standard.** The Metadata Librarian drafts a record in the standard the merged set
follows, from the standard's definition and the project's facts, and writes it through the
standard's codec with `conforms_to` and `media_type` set. It asks one question for each gap, named by
the property's path (invariant 5), and places the researcher's answer as given. A standard that is
not registered is an abstention, `capability_not_implemented`, as now. DataCite in JSON is the only
standard built (#1359 makes the Librarian read the definition, and #1360 adds Dublin Core).

**Converting a record.** A conversion reads a record into the pivot with its standard's definition
and writes the pivot into another with the target's, so that n standards need n definitions, not n²
converters. A property is placed if it has a pivot term in both. The result lists what was not
placed, as a platform's item lists `unplaced` ([Deposit](deposit.md), *Depositing through an API*),
and what was reduced, such as a structured value written as text. A conversion is a package derived
from the approved record (invariant 2). Whether a project that deposits in more than one repository
holds a record in each standard, and how a person approves it, is TODO(#1363).

**Where the code lives.** The codecs and definitions are a member of their own, `metadata-records/`
(distribution `data-director-metadata-records`), that imports no other member, as `inventory/` and
`mcp-pid/` do not. The harness and each agent that drafts or reads a record depend on it, and the
[System and boundaries](system.md) graph says so. It is not in `sdk/`, which holds only the
contract, and not in the harness, which no agent may import. Nothing in it speaks the Data Director
contract, so it can be published and used without the rest ("Build for reuse" in the root `AGENTS.md`); the
agents and the harness add the contract's parts, such as classes, evidence and outcomes.

## Rationale

- **Definitions beside a requirement-set mechanism that already works.** The deposit check already
  reads a record as RDF through a table and generates its shapes. Taking that table out of the sets,
  completing it, and letting a set name only what it requires, makes one description of each
  standard serve validation, packaging, drafting and conversion.
- **One name for a property in every serialisation**, so that a researcher's answer, a question's
  identifier and a requirement stay the same when a record is written in another serialisation.
- **A pivot of existing terms, and a reported loss, not a promise of equivalence.** Standards differ
  in what they can say, and no vocabulary says everything; DataCite has no lineage, and schema.org
  has no free term for it. Reporting what was not placed is honest, and the researcher or steward
  can see what a conversion costs before a repository sees the record.
- **Completeness in the definition, not the set.** A set lists only what is required or
  recommended, but a conversion needs every property, so the pivot term lives in the definition.
- **A standard needs no profile key.** The profile holds a deployment's choices about what may act
  on its behalf. A function from a record to bytes is not one, and installing the standard is
  enough.
- **A member of its own**, so that others can use the codecs and mappings without Data Director, as
  the Build for reuse rules ask, and so that the harness, which depends on `sdk/` alone, and the
  agents do not copy it (`scripts/check_duplication.py`).

## Rejected alternatives

- **DataCite as the canonical model, with every other standard crosswalked through it.** DataCite is
  a citation schema. Everything it cannot hold would be lost on the way through it, and a researcher
  depositing in DDI or ISO 19115 would be held to a citation record.
- **A Data Director metadata model as the pivot.** It would be a fourth format that no repository
  reads, it would need a mapping to every standard in both directions, and it would invent terms
  where external ones exist ([Contract](contract.md), *Vocabularies*).
- **A converter for each pair of standards.** n standards would need n² of them, each to review and
  keep working, and two repositories that take the same standard would share nothing.
- **A drafter for each standard.** The questions, the rules against inventing a value and the place
  of a model are the same for every standard and would be written again for each.
- **JSON-LD as the serialisation of every record.** Repositories take their own serialisation, such
  as OAI-DC or ISO 19139 XML, so a record in JSON-LD would still need writing in it.
- **Standard definitions as deployment configuration beside the requirement sets.** A steward who
  edits a repository's licence list should not be able to change where a standard writes a title.
  Two kinds of file with two owners need two places.
- **A model that maps or converts at run time.** A misread mapping would become the definition of a
  correct record, and each conversion would differ. The same reasoning rejected requirements drafted
  by an agent ([Deposit](deposit.md), *Rejected alternatives*). A model may help a person write a
  definition, which is then reviewed like a set.
- **A published JSON Schema or XSD per standard as the only check.** Its errors are not in the
  validation report's vocabulary ([Deposit](deposit.md), *Rejected alternatives*); see *Open
  questions* for what is decided about it.
- **The codecs in `sdk/` or in the harness.** `sdk/` holds only the contract, and an agent may not
  import the harness. A copy in each agent is what `scripts/check_duplication.py` exists to stop.

## Non-functional requirements

- **Reproducibility.** The same tree, definition and codec give the same bytes on any host, so a
  digest recorded at approval is the digest of what is deposited (invariants 4 and 12).
- **Security.** Invariant 13. A record's text is data: it is parsed, never executed, and a parser
  makes no network call.
- **Portability.** The library is pure Python, makes no network call and holds no credential. A
  dependency it needs, such as an XML parser, is registered in [Dependencies](dependencies.md) with
  a fallback behind the codec's interface, in the pull request that adds it.
- **Honesty about coverage.** A definition says which properties of its standard it covers. A
  record in a standard that a definition covers only in part says so, as a repository without an
  override is told its own form is not checked.

## Open questions

- Which XML parser the XML codec uses, and its fallback: TODO(#1360).
- Which Dublin Core: the 15 elements OAI-DC carries, Dublin Core Terms, or both: TODO(#1360).
- Whether the harness also checks a record against its standard's published schema, reporting each
  error as an `sh:Violation`, or leaves that to the codec's tests: TODO(#1360).
- How the harness chooses among several standards a repository declares, and how a person chooses
  one explicitly, as for Croissant (#933): TODO(#1362).
- Whether a conversion for a second repository is a derived package or a document a person approves:
  TODO(#1363).
- How a standard's controlled vocabularies are reached and cited is decided for the subject
  classifications a repository names (ANZSRC, OECD): through the tool gateway, from
  `mcp-subjects`, each suggested field citing its record ([Drafting documents](drafting.md),
  invariant 7). Which terminology services keywords and other terms come from: TODO(#956).
