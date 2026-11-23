"""The Storage Adviser's decisions: which of the institution's storage services may hold a
project's data while it runs, in what order, with what concerns, and which questions a storage and
backup plan answers (docs/specs/agents.md). Deterministic over what the researcher said and what
the profile vouches for; nothing here judges a service the profile says nothing about.

- A service is left out for personal data unless the profile says it is approved for sensitive
  data. An unknown approval is never taken as approval.
- A service the researcher may use has a concern for each thing to check before choosing it: an
  approval the profile does not state when personal data are possible, an allowance below the
  expected volume, no access for people outside the institution when they need it, and a charge.
- Services with fewer concerns come first; otherwise the profile's order stands.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from dd_agent_advisor_storage.classes import PersonalDataAnswer, StorageNeeds
from dd_sdk.contract.facts import InstitutionStorage, StorageKind

KINDS = {
    StorageKind.INSTITUTIONAL_FILESTORE: "File storage the institution runs for research data",
    StorageKind.INSTITUTIONAL_CLOUD: "Cloud storage the institution provides",
    StorageKind.MANAGED_CLOUD: "A cloud service the institution has approved",
    StorageKind.SECURE_ENVIRONMENT: "A secure environment for sensitive data",
}

# The questions every storage and backup plan answers, after the core requirement "Storage and
# backup during the project" (dd_dmp_template, Science Europe's guide).
QUESTIONS = (
    "How many copies of the data will there be, and is at least one kept in another place?",
    "How often are the data backed up, and has restoring them from a backup been tried?",
    "Who will have access to the data, and how will access be given and taken away?",
    "What will happen to the data when the project ends, or when someone leaves it?",
)
PERSONAL_QUESTIONS = (
    "How will personal data be kept secure: encrypted, and on a service approved for them?",
)


@dataclass
class Judged:
    entry: InstitutionStorage
    offers: list[str] = field(default_factory=list)
    concerns: list[str] = field(default_factory=list)


@dataclass
class Judgement:
    options: list[Judged]
    excluded: list[tuple[InstitutionStorage, str]]
    questions: list[str]


def judge(needs: StorageNeeds) -> Judgement:
    """The services in `needs.institution_storage`, judged against what the researcher said."""
    options: list[Judged] = []
    excluded: list[tuple[InstitutionStorage, str]] = []
    personal = needs.involves_personal_data
    for entry in needs.institution_storage:
        if personal is PersonalDataAnswer.YES and entry.approved_for_sensitive is not True:
            excluded.append((entry, _not_approved(entry)))
            continue
        options.append(Judged(entry, _offers(entry), _concerns(entry, needs)))
    options.sort(key=lambda judged: len(judged.concerns))  # stable: the profile's order stands
    questions = list(QUESTIONS)
    if personal is not PersonalDataAnswer.NO:
        questions.extend(PERSONAL_QUESTIONS)
    return Judgement(options, excluded, questions)


def _not_approved(entry: InstitutionStorage) -> str:
    if entry.approved_for_sensitive is False:
        return "The institution does not approve it for personal or sensitive data."
    return "The institution's profile does not say it is approved for personal or sensitive data."


def _offers(entry: InstitutionStorage) -> list[str]:
    offers = [KINDS[entry.storage_kind]] if entry.storage_kind is not None else []
    if entry.approved_for_sensitive:
        offers.append("Approved for personal or sensitive data")
    if entry.storage_backup:
        offers.append(f"Backup: {entry.storage_backup}")
    if entry.allowance_gb is not None:
        offers.append(f"Up to {entry.allowance_gb:g} GB without charge")
    if entry.allows_external_collaborators:
        offers.append("People outside the institution can be given access")
    return offers


def _concerns(entry: InstitutionStorage, needs: StorageNeeds) -> list[str]:
    concerns: list[str] = []
    if (
        needs.involves_personal_data is not PersonalDataAnswer.NO
        and entry.approved_for_sensitive is not True
    ):
        concerns.append(
            "Not stated to be approved for personal data: use it only if there is none."
        )
    volume, allowance = needs.expected_volume_gb, entry.allowance_gb
    if volume is not None and allowance is not None and volume > allowance:
        concerns.append(
            f"The project expects about {volume} GB, more than its {allowance:g} GB allowance."
        )
    if needs.external_collaborators and entry.allows_external_collaborators is not True:
        concerns.append("People outside the institution may not be able to get access.")
    if entry.charges_for_storage:
        concerns.append("The institution charges for storage here: check the cost.")
    if entry.storage_backup is None:
        concerns.append("The profile does not say how the service keeps copies: ask.")
    return concerns
