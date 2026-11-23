"""The core requirements for a Data Management Plan, after Science Europe's.

Science Europe's *Practical Guide to the International Alignment of Research Data Management*
(extended edition, 2021, CC BY 4.0) sets out six core requirements that most funders' templates
map onto, among them UKRI's councils' and Horizon Europe's. Each requirement is a `Section` here,
with its questions in this library's own paraphrase.

Two questions are this library's additions, after the STFC/UKRI and UK Data Service guidance on
Data Management Plans: how long the data will be kept, and how and when the plan itself will be
reviewed and updated, since a plan is kept up to date as the research proceeds.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Section:
    """One core requirement of a Data Management Plan."""

    # A stable label, such as "data-collection".
    id: str
    # The heading a plan written to the requirements gives it.
    heading: str
    # What the section says, in one sentence a researcher can answer.
    summary: str
    # The requirement's questions, each of which a complete section answers.
    questions: tuple[str, ...]


SECTIONS: tuple[Section, ...] = (
    Section(
        "data-collection",
        "Data description and collection",
        "what data the project will collect, produce or reuse, of what types and formats and "
        "in what volume, and how.",
        (
            "How will new data be collected or produced, and how will existing data be reused?",
            "What data, of which types and formats and in what volume, will be collected or "
            "produced?",
        ),
    ),
    Section(
        "documentation-quality",
        "Documentation and data quality",
        "the documentation and metadata that will accompany the data, and how their quality "
        "will be checked.",
        (
            "What metadata and documentation, such as the methods, how the data were collected "
            "and how they are organised, will accompany the data?",
            "What measures will control the data's quality?",
        ),
    ),
    Section(
        "storage-backup",
        "Storage and backup during the project",
        "where the data will be stored and backed up while the project runs, and how they will "
        "be kept secure.",
        (
            "How will the data and metadata be stored and backed up during the project?",
            "How will the data be kept secure, and sensitive data protected?",
        ),
    ),
    Section(
        "legal-ethical",
        "Legal and ethical requirements",
        "how personal data, intellectual property and ownership will be handled, and what "
        "ethical issues and codes of conduct apply.",
        (
            "If personal data are processed, how will the project comply with the law on "
            "personal data and its security?",
            "How will other legal matters, such as intellectual property and ownership, be "
            "managed?",
            "What ethical issues and codes of conduct apply, and how will they be taken into "
            "account?",
        ),
    ),
    Section(
        "sharing-preservation",
        "Data sharing and long-term preservation",
        "how and when the data will be shared, under what licence and restrictions, where and "
        "for how long they will be preserved, and how they will get a persistent identifier.",
        (
            "How and when will the data be shared, and are there restrictions on sharing?",
            "How will the data to keep be chosen, and where will they be preserved in the long "
            "term?",
            "How long will the data be kept, and why?",
            "What methods or software will be needed to access and use the data?",
            "How will each dataset get a unique and persistent identifier?",
        ),
    ),
    Section(
        "responsibilities-resources",
        "Responsibilities and resources",
        "who will be responsible for managing the data, what time and money will be spent on "
        "it, and how this plan will be kept up to date.",
        (
            "Who will be responsible for data management?",
            "What resources will be given to managing the data and making them FAIR?",
            "How and when will this plan be reviewed and updated, and by whom?",
        ),
    ),
)
