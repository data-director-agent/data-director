# Acknowledgements

Data Director rests on the work of a community, on registries that people curate and on open
standards and software. This page thanks them. What each source's licence asks of a reuse is on
[Sources and licences](sources-and-licences.md).

## The Blueprint and its Working Group

This is a reference implementation of the
[Data Director Agentic AI Blueprint](../../blueprint/README.md) ([Research Data Alliance](https://www.rd-alliance.org),
CC BY 4.0, [doi:10.15497/RDA00157](https://doi.org/10.15497/RDA00157)). The Blueprint was written by
the RDA Data Director Agentic AI Blueprint Working Group, facilitated by Connie Clare (RDA) with
support from Trish Radotic (RDA Secretariat). Benjamin Wright-Jones and George Earl (Microsoft)
developed its reference architecture. Hilary Hanahoe (RDA Secretary General) and Marcy Collinson
(Microsoft) brought the public-private partnership between RDA and Microsoft to fruition.

Every member of the Working Group is listed in
[Appendix C: Acknowledgements](../../blueprint/appendix-c-acknowledgements.md), and the
organisations that plan to implement it in
[Appendix D](../../blueprint/appendix-d-implementors.md). We thank them all.

## This implementation

The software is developed by the University of Sheffield and released under the
[MIT licence](https://github.com/data-director-agent/data-director/blob/main/LICENSE). Its
authors are Joe Salvador Thornhill Heffer (University of Sheffield), Raymond Uzwyshyn (University
of California, Riverside) and Tian Heng Zhuang, as recorded in
[`CITATION.cff`](https://github.com/data-director-agent/data-director/blob/main/CITATION.cff),
which also lists the works it builds on and tells you how to cite it. Everyone who has opened an
issue, reviewed a change or contributed code is listed on the repository's
[contributors page](https://github.com/data-director-agent/data-director/graphs/contributors),
and the [Contributing guide](../../../CONTRIBUTING.md) explains how to join them.

The design has been discussed in the Working Group's reference implementation meetings since
October 2026. We thank the participants for the ideas they brought:

- Patricia Buendia (Lifetime Omics): a biomedical workflow with human approval gates, and pilot datasets.
- Lars Eklund (Uppsala University): a versioned requirements specification in the repository, and archiving releases on Zenodo.
- Seonyoung Kim (Washington University): coordination with the RDA AI in Research Interest Group.
- Allyson Lister (University of Oxford): the Data Director suggests changes for a person to confirm, rather than changing data itself.
- Ugochi Okengwu (University of Port Harcourt).
- Monica Palmero Fernandez (University of Oxford): a joint Sheffield and Oxford implementation.
- Pengyin Shan (NCSA, University of Illinois Urbana-Champaign): the agreements and approvals needed before real data is used.
- Slava Tykhonov (CODATA): verified agent identities with signed inputs and outputs, ODRL for policies, and evaluation.
- Raymond Uzwyshyn (University of California, Riverside): a persona-based design of six agents.
- Carlo Maria Zwölf (LUX, Observatoire de Paris): a post-mortem of an end-to-end deposit prototype.

## Registries and services

The agents' advice is only as good as the registries behind it, and we are grateful to the people
and organisations who curate them. Each record an agent relies on is cited in its evidence.

| Source | What it gives Data Director | Credit |
|---|---|---|
| [FAIRsharing](https://fairsharing.org) | Standards, repositories and policies | Sansone et al. 2019, [doi:10.1038/s41587-019-0080-8](https://doi.org/10.1038/s41587-019-0080-8). CC BY-SA 4.0. |
| [re3data](https://www.re3data.org) | The Registry of Research Data Repositories | [doi:10.17616/R3D](https://doi.org/10.17616/R3D). CC0. |
| [DataCite](https://datacite.org) | Repository records, and DOI metadata | CC0. |
| [Crossref](https://www.crossref.org) | DOI, journal and grant metadata | Facts, openly available. |
| [ROR](https://ror.org) | Research organisation identifiers | The Research Organization Registry. CC0. |
| [ORCID](https://orcid.org) | A researcher's own public record, when they choose to use it | ORCID's public API, for non-commercial use. |
| [OpenAlex](https://openalex.org) | Journals by ISSN and title | CC0. |
| [OpenAIRE Graph](https://graph.openaire.eu) | Projects and funding | CC BY 4.0. |
| [DOAJ](https://doaj.org) | Open access journals' terms | The Directory of Open Access Journals. CC0. |
| [Jisc Open Policy Finder](https://openpolicyfinder.jisc.ac.uk) | Publisher and journal open access policies | Read live and never kept. CC BY-NC-ND 4.0; API for non-commercial use. |
| [PRONOM](https://www.nationalarchives.gov.uk/PRONOM/) | File format identification and descriptions | The National Archives. Contains public sector information licensed under the Open Government Licence v3.0. |
| [SPDX License List](https://spdx.org/licenses/) | Licence identifiers | CC0. |
| [GA4GH Data Use Ontology](https://github.com/EBISPOT/DUO) | Data use conditions | CC BY 4.0. |
| [UCUM](https://ucum.org) | Units of measure | Regenstrief Institute. UCUM licence. |
| ANZSRC 2020 Fields of Research | Subject classification | Australian Bureau of Statistics and Stats NZ. CC BY 4.0. |
| OECD Fields of Research and Development | Subject classification | OECD, as source and copyright owner. |

The exact credit each publisher asks for is in
[`app/config/credits.yaml`](https://github.com/data-director-agent/data-director/blob/main/app/config/credits.yaml),
and the app shows it on its Sources and licences page.

## Standards and open software

Data Director adopts open standards rather than inventing its own: the
[Agent2Agent (A2A) protocol](https://a2a-protocol.org) and the
[Model Context Protocol (MCP)](https://modelcontextprotocol.io) for agents and tools, Agent Skills
for instructions, [LinkML](https://linkml.io) and SHACL for formats, and
[OpenTelemetry](https://opentelemetry.io) for tracing. It is built with Python, `uv`, Ruff,
Pydantic, React and Vite, and this site with [MkDocs](https://www.mkdocs.org/) and the
[Material](https://squidfunk.github.io/mkdocs-material/) theme.

The app uses the [Inter](https://rsms.me/inter/) typeface (SIL Open Font License 1.1) and the
[Lucide](https://lucide.dev) (ISC) and [Octicons](https://primer.style/octicons/) (MIT) icons. The
ORCID iD icon is ORCID's trademark. The full list of third-party material is in the
[Notice](../../../NOTICE.md).

## Corrections

If we have left out someone who should be credited, or credited a source in a way its publisher
would not want, please [open an issue](https://github.com/data-director-agent/data-director/issues)
and we will correct it.
