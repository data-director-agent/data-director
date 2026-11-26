# Data Director

Data Director is an assistant for looking after your research data. You tell it about your project
in your own words, and it helps you plan how the data will be managed, work out what your funder
and institution expect, choose a repository, describe your data well and get it ready to share.

It is built from a team of small specialist agents, each helping with one part of the job, and a
conversation that brings them together. The agents give advice and draft documents. You decide
everything, and you can see what each of them did and where its advice came from.

!!! warning "Alpha: try it with test data only"
    Data Director is early software, built in the open, and it will change. Please use made-up or
    already-public data while you try it, and treat its advice as a draft to check. The
    [alpha usage agreement](user-guide/usage-agreement.md) is short and worth reading first.

## Who it is for

- **Researchers**: students, research staff and principal investigators who have to manage, document
  and share data and do not do it every day. You do not need to know metadata standards or
  repository jargon; the Data Director explains them as it goes.
- **Research teams**: a project can be shared with colleagues, who see the same documents and
  decisions ([Working on a project with others](user-guide/members.md)).
- **Data stewards, librarians and research support staff**: people who help researchers with their
  data. Data Director does not replace you. It does the routine preparation so that researchers
  arrive with better questions, and it hands over the matters that need a person
  ([Data Steward's Guide](steward-guide/index.md)).

## When it helps in a research project

You can use Data Director at any point from the first plan to long after publication. It is
organised around six stages, and you can join at the one that matches where you are:

| Where you are | What Data Director helps with |
|---|---|
| **Planning a project**, before you collect anything | Describing the data you expect to produce, a data management plan, where to store data while you work, which standards and file formats to use |
| **You have data and want to share them** | What your funder, journal and institution require, whether anything is sensitive, whether an embargo is needed, which repository suits |
| **You are ready to deposit** | Choosing the repository, describing the dataset, a README and data dictionary, a licence, checking the record, and a deposit package to take to the repository |
| **After publication** | Keeping your plan up to date, and checking and improving the records of datasets you have already published |

[The workflow](user-guide/workflow.md) explains these stages in plain words.

## What it does not do

- It never sees your data files. It works from a short description of them that you make on your
  own computer ([Making an inventory](user-guide/making-an-inventory.md)).
- It does not publish anything. It gets your project ready, and you deposit in the repository
  yourself ([Depositing your data](user-guide/depositing.md)).
- It does not give legal or ethics advice, and it does not decide for you which repository,
  licence or access level to use.
- It does not hide its working. Every answer has an [outcome](user-guide/outcomes.md), the sources
  it rests on and a [record](user-guide/records.md) you can read later.

## Where to start

- **[Getting started](user-guide/getting-started.md)**: open the app and have your first
  conversation, in about ten minutes.
- **[The workflow](user-guide/workflow.md)**: where you are in the research data lifecycle and what
  to do next.
- **[User guide](user-guide/index.md)**: everything the app does, one page at a time.

Other guides are for other readers:

- **[Data Steward's Guide](steward-guide/index.md)**: for the people who support researchers, own
  the institution's policy and answer the matters researchers hand over.
- **[Operations guide](operations/index.md)**: for the people who install and run an instance,
  including the AI models it may call.
- **[Developer guide](developer-guide/index.md)**: set up the repository, write an agent and work
  on these pages.
- **[Reference](reference/index.md)**: the contract, specifications, glossary and conformance
  report.

You can also help without writing code, by telling the project where its advice falls short:
see [Giving feedback](user-guide/feedback.md). How this site and the project handle personal data
is in the [privacy notice](privacy.md).

## Where it comes from

Data Director is a reference implementation of the Research Data Alliance (RDA)
[Data Director Agentic AI Blueprint](https://www.rd-alliance.org/groups/data-director-agentic-ai-blueprint/outputs/data-director-agentic-ai-tool-blueprint/),
published at <https://doi.org/10.15497/RDA00157>. The Blueprint is the community's specification
of what such a tool should do. It followed an RDA community consultation, reported in
[Global Community Priorities for Agentic AI in Research. Community Consultation Results](https://doi.org/10.15497/RDA00151)
(<https://doi.org/10.15497/RDA00151>).

Related work:

- [RDA for Artificial Intelligence Cross-fertilisation Summary](https://doi.org/10.15497/RDA00160)
  (RDA Secretariat, 2026), <https://doi.org/10.15497/RDA00160>.
- [The Research Data Director: A Persona-Based Agentic AI Blueprint and Application for FAIR Research Data, Metadata, and Schema and Crosswalk Workflows](https://doi.org/10.5281/zenodo.23670411)
  (Uzwyshyn, 2026), a companion persona-based blueprint, <https://doi.org/10.5281/zenodo.23670411>.

The software is archived on Zenodo, and is cited as
[doi:10.5281/zenodo.23735878](https://doi.org/10.5281/zenodo.23735878).

## Acknowledgements

Data Director implements the RDA's Data Director Agentic AI Blueprint and reads registries such as
re3data and FAIRsharing that other people curate. [Acknowledgements](reference/acknowledgements.md)
thanks them, and [Sources and licences](reference/sources-and-licences.md) lists each credit and
licence.
