"""Pydantic mirrors of the LinkML classes in schema/data_director.yaml.

The LinkML source is the contract; these models are how Python code constructs and reads
documents that conform to it. A test asserts that instances of every model here validate
against the generated JSON Schema, so the two cannot drift silently. Field names and enum
values are identical to the LinkML slot and permissible-value names on purpose.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, SerializeAsAny, model_validator

UUID7_PATTERN = r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
SHA256_PATTERN = r"^[0-9a-f]{64}$"
POLICY_BUNDLE_REF_PATTERN = r"^profile:[a-z0-9][a-z0-9.-]*@v[0-9]+$"
IRI_PATTERN = r"^[a-z][a-z0-9+.-]*:\S+$"
VERSION_PATTERN = r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$"
# One line of 1 to 80 characters (Reply.conversation_title).
CONVERSATION_TITLE_PATTERN = r"^.{1,80}$"
# A drafter's question about a gap, derived from the gap (docs/specs/drafting.md).
QUESTION_ID_PATTERN = r"^q-[0-9a-f]{16}$"
CONVERSATION_TITLE_MAX = 80
# A project's title (Message.project_title), and a name a model gives one (Reply.new_project_title).
PROJECT_TITLE_PATTERN = r"^.{1,200}$"
NEW_PROJECT_TITLE_PATTERN = CONVERSATION_TITLE_PATTERN
NEW_PROJECT_TITLE_MAX = CONVERSATION_TITLE_MAX
# A choice question offers between 2 and 12 options (Question.question_options).
CHOICE_OPTIONS_MIN = 2
CHOICE_OPTIONS_MAX = 12
# A reply asks between 1 and 8 questions (Reply.reply_questions).
QUESTIONS_MAX = 8
# An answer in the researcher's own words: one line for a short text question, several for a
# long one; a choice question's own-words answer is held to the short bound (QuestionAnswer).
SHORT_TEXT_MAX = 200
LONG_TEXT_MAX = 4000
# A question's identifier within its reply (Question.question_key, QuestionAnswer.answered_key).
QUESTION_KEY_PATTERN = r"^[a-z][a-z0-9-]{0,39}$"


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


def new_invocation_id() -> str:
    """UUIDv7 (RFC 9562), from the standard library. docs/specs/contract.md."""
    return str(uuid.uuid7())


def now() -> datetime:
    return datetime.now(UTC)


# --- Enumerations ---------------------------------------------------------------------------


class OutcomeStatus(StrEnum):
    SUCCEEDED = "succeeded"
    ABSTAINED = "abstained"
    REFERRED = "referred"
    FAILED = "failed"
    SUSPENDED = "suspended"


class ReasonCode(StrEnum):
    # abstained
    NO_QUALIFYING_RESOURCE = "no_qualifying_resource"
    NO_CANDIDATES_RETRIEVED = "no_candidates_retrieved"
    REGISTRY_UNAVAILABLE = "registry_unavailable"
    NOT_APPLICABLE = "not_applicable"
    INSUFFICIENT_INPUT = "insufficient_input"
    CAPABILITY_NOT_IMPLEMENTED = "capability_not_implemented"
    # referred
    REQUIRES_HUMAN_JUDGEMENT = "requires_human_judgement"
    POLICY_REQUIRES_APPROVAL = "policy_requires_approval"
    OUTSIDE_AGENT_SCOPE = "outside_agent_scope"
    # abstained: a person's own model account could not be used (docs/specs/model-accounts.md)
    MODEL_ACCOUNT_MISSING = "model_account_missing"
    MODEL_ACCOUNT_REJECTED = "model_account_rejected"
    MODEL_ACCOUNT_LIMIT = "model_account_limit"


class ModelAccount(StrEnum):
    """Whose account paid for a model call: a person's own or the deployment's
    (docs/specs/model-accounts.md)."""

    OWN = "own"
    DEPLOYMENT = "deployment"


class Derivation(StrEnum):
    TEMPLATE = "template"
    MODEL = "model"
    LEXICAL = "lexical"
    REGISTRY = "registry"


class DocumentKind(StrEnum):
    METADATA_RECORD = "metadata_record"
    README = "readme"
    DATA_DICTIONARY = "data_dictionary"
    DMP = "dmp"
    OTHER = "other"


class VersionState(StrEnum):
    """The state of one version of a project document (docs/specs/projects.md)."""

    PROPOSED = "proposed"
    APPROVED = "approved"
    REJECTED = "rejected"


class EnergyMethod(StrEnum):
    NOT_MEASURED = "not_measured"
    ESTIMATED = "estimated"
    MEASURED = "measured"


class GroundingMode(StrEnum):
    """The grounding contract an agent declares (docs/specs/grounding.md)."""

    RETRIEVAL = "retrieval"
    INPUT_ONLY = "input_only"
    NONE = "none"
    DELEGATION = "delegation"


class PrincipalKind(StrEnum):
    PERSON = "person"
    ACCOUNTABLE_ROLE = "accountable_role"


class Assurance(StrEnum):
    ASSERTED = "asserted"
    AUTHENTICATED = "authenticated"


class StepState(StrEnum):
    STARTED = "started"
    DONE = "done"
    SKIPPED = "skipped"


class QuestionKind(StrEnum):
    CHOICE = "choice"
    SHORT_TEXT = "short_text"
    LONG_TEXT = "long_text"


class TurnRole(StrEnum):
    USER = "user"
    AGENT = "agent"


class IdentificationMethod(StrEnum):
    SIGNATURE = "signature"
    CONTAINER = "container"
    EXTENSION = "extension"
    NONE = "none"
    RESEARCHER = "researcher"


class FileRole(StrEnum):
    DATA = "data"
    DOCUMENTATION = "documentation"
    CODE = "code"
    OTHER = "other"


class Obligation(StrEnum):
    REQUIRED = "required"
    RECOMMENDED = "recommended"


# --- Requirement sets -------------------------------------------------------------------------
# What a deposit must or should have (docs/specs/deposit.md): the deployment's configuration, which
# the harness loads and merges for the repository a researcher chose. Not an input or a payload of
# any agent.


class RequirementField(Frozen):
    property: str
    qualifier: dict[str, Any] | None = None
    schema_org: str
    obligation: Obligation
    form_label: str | None = None


class RequirementSet(Frozen):
    """A metadata standard's requirements, or one repository's override of them
    (docs/specs/deposit.md)."""

    schema_class: Literal["RequirementSet"] = "RequirementSet"
    requirement_set_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    version: int
    title: str
    url: str | None = None
    conforms_to: str
    re3data_names: list[str] = Field(default_factory=list)
    re3data_id: str | None = Field(default=None, pattern=r"^r3d[0-9]{9}$")
    fields: list[RequirementField] = Field(default_factory=list)
    required_documents: list[DocumentKind] = Field(default_factory=list)
    recommended_documents: list[DocumentKind] = Field(default_factory=list)
    media_types: list[str] = Field(default_factory=list)
    max_file_size: int | None = None
    max_item_size: int | None = None
    licences: list[str] | None = None
    guidance: list[str] = Field(default_factory=list)
    unconfirmed: list[str] = Field(default_factory=list)


class RequirementSetUse(Frozen):
    ref: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*@v[0-9]+$")
    sha256: str = Field(pattern=SHA256_PATTERN)


class RepositoryRequirements(Frozen):
    """The merged requirements of the repository a researcher chose (docs/specs/deposit.md)."""

    re3data_id: str = Field(pattern=r"^r3d[0-9]{9}$")
    repository_name: str
    conforms_to: str
    requirement_sets: list[RequirementSetUse]
    fields: list[RequirementField] = Field(default_factory=list)
    required_documents: list[DocumentKind] = Field(default_factory=list)
    recommended_documents: list[DocumentKind] = Field(default_factory=list)
    media_types: list[str] = Field(default_factory=list)
    max_file_size: int | None = None
    max_item_size: int | None = None
    licences: list[str] | None = None
    warnings: list[str] = Field(default_factory=list)
    unconfirmed: list[str] = Field(default_factory=list)
    repository_url: str | None = None


# --- Inputs -----------------------------------------------------------------------------------
# Every input class carries `schema_class` as a type designator with a single literal value. The
# core defines the conversation's Message, a project's FileInventory and the drafters'
# DraftRequest (below); every other input class belongs to its agent (docs/specs/contract.md), and
# the harness holds such an input as an `OpenInput`.


class ConversationTurn(Frozen):
    role: TurnRole
    turn_text: str
    turn_agent_id: str | None = None
    turn_agent_version: str | None = None
    turn_invocation_id: str | None = Field(default=None, pattern=UUID7_PATTERN)


class InventorySummary(Frozen):
    """What the inventory a project holds is, without its files (docs/specs/projects.md)."""

    inventory_digest: str = Field(pattern=SHA256_PATTERN)
    inventory_file_count: int
    inventory_tool: str
    inventory_tool_version: str
    inventory_made_at: datetime
    inventory_limitations: list[str] = Field(default_factory=list)


class DocumentationSummary(Frozen):
    """What one document attached to a project is, without its text (docs/specs/projects.md)."""

    documentation_name: str
    documentation_digest: str = Field(pattern=SHA256_PATTERN)
    documentation_media_type: str
    documentation_size: int
    documentation_added_at: datetime


class AffiliationKind(StrEnum):
    EMPLOYMENT = "employment"
    EDUCATION = "education"
    QUALIFICATION = "qualification"
    INVITED_POSITION = "invited_position"
    DISTINCTION = "distinction"
    MEMBERSHIP = "membership"
    SERVICE = "service"


class ResearcherLink(Frozen):
    link_title: str | None = None
    link_url: str


class ExternalIdentifier(Frozen):
    identifier_type: str
    identifier_value: str
    identifier_url: str | None = None


class Affiliation(Frozen):
    put_code: str
    affiliation_kind: AffiliationKind
    organisation_name: str
    organisation_identifier: str | None = None
    organisation_identifier_scheme: str | None = None
    department: str | None = None
    role_title: str | None = None
    start_year: int | None = None
    end_year: int | None = None


class ResearcherWork(Frozen):
    put_code: str
    work_title: str
    work_type: str | None = None
    publication_year: int | None = None
    journal_title: str | None = None
    work_identifiers: list[ExternalIdentifier] = Field(default_factory=list)


class ResearcherFunding(Frozen):
    put_code: str
    funding_title: str
    funding_type: str | None = None
    funder_name: str
    funder_identifier: str | None = None
    funder_identifier_scheme: str | None = None
    award_identifier: str | None = None
    start_year: int | None = None
    end_year: int | None = None


class ResearcherRecord(Frozen):
    """What one researcher in a project chose to keep from their public ORCID record, in ORCID's
    own words (docs/specs/projects.md). Never an email address."""

    orcid_id: str
    researcher_name: str | None = None
    other_names: list[str] = Field(default_factory=list)
    biography: str | None = None
    keywords: list[str] = Field(default_factory=list)
    country: list[str] = Field(default_factory=list)
    researcher_links: list[ResearcherLink] = Field(default_factory=list)
    external_identifiers: list[ExternalIdentifier] = Field(default_factory=list)
    affiliations: list[Affiliation] = Field(default_factory=list)
    works: list[ResearcherWork] = Field(default_factory=list)
    works_omitted: int | None = None
    fundings: list[ResearcherFunding] = Field(default_factory=list)
    record_retrieved_at: datetime
    record_source: str


class StepProgress(Frozen):
    """How far one process-flow step has gone, as the project log shows it; a step left out is
    open (docs/specs/orchestration.md)."""

    step_id: str = Field(pattern=r"^[a-z]+\.[a-z-]+$")
    step_state: StepState


class QuestionAnswer(Frozen):
    """The researcher's answer to one question of a reply: the values of the options chosen, or
    the answer in their own words. Whether it fits its question is checked against the question
    (`dd_harness.conversations.answer_problem`)."""

    answered_key: str = Field(pattern=QUESTION_KEY_PATTERN)
    answer_values: list[str] = Field(default_factory=list)
    answer_words: str | None = Field(default=None, max_length=LONG_TEXT_MAX)


class ReplyAnswers(Frozen):
    """The researcher's answers to the questions the turn before asked, given together, one for
    each question answered (docs/specs/orchestration.md)."""

    answer_to: str = Field(pattern=UUID7_PATTERN)
    # The bound is not in the schema (#333).
    given_answers: list[QuestionAnswer] = Field(min_length=1, max_length=QUESTIONS_MAX)

    @model_validator(mode="after")
    def _one_answer_a_question(self) -> ReplyAnswers:
        keys = [a.answered_key for a in self.given_answers]
        if len(set(keys)) != len(keys):
            raise ValueError("each question is answered at most once")
        return self


class Message(Frozen):
    """One conversational turn and the conversation so far (docs/specs/orchestration.md). The
    conductor fills `project_inventory`, `project_entry`, `project_progress`, `project_title`,
    `project_title_by_researcher`, `project_entry_by_researcher`, `project_documentation` and
    `project_researchers` from the conversation's project; a caller never does."""

    schema_class: Literal["Message"] = "Message"
    message_text: str
    history: list[ConversationTurn] = Field(default_factory=list)
    project_inventory: InventorySummary | None = None
    reply_answers: ReplyAnswers | None = None
    project_entry: int | None = Field(default=None, ge=1, le=3)  # bounds not in the schema (#333)
    project_progress: list[StepProgress] | None = None
    project_title: str | None = Field(default=None, pattern=PROJECT_TITLE_PATTERN)
    project_title_by_researcher: bool | None = None
    project_documentation: list[DocumentationSummary] | None = None
    project_entry_by_researcher: bool | None = None
    project_researchers: list[ResearcherRecord] | None = None


class TableField(Frozen):
    """One field of a table, as a Frictionless Table Schema field descriptor."""

    name: str
    field_type: str | None = None
    field_format: str | None = None
    field_description: str | None = None


class InventoryFile(Frozen):
    file_path: str = Field(pattern=r"^[^/]")
    file_size: int
    file_sha256: str = Field(pattern=SHA256_PATTERN)
    file_media_type: str | None = None
    file_pronom_ids: list[str] = Field(default_factory=list)
    file_identified_by: IdentificationMethod
    file_fields: list[TableField] = Field(default_factory=list)
    file_description: str | None = None
    file_role: FileRole | None = None


class FileInventory(Frozen):
    """The facts about a dataset's files a project holds in place of the files
    (docs/specs/projects.md)."""

    schema_class: Literal["FileInventory"] = "FileInventory"
    inventory_files: list[InventoryFile] = Field(default_factory=list)
    inventory_tool: str
    inventory_tool_version: str
    inventory_identified_with: str | None = None
    inventory_made_at: datetime
    inventory_limitations: list[str] = Field(default_factory=list)


class OpenInput(Frozen):
    """An input held as the document it is, checked against its class schema, not a model.

    What the harness reads a request's input as: it knows an agent's classes only by their schemas
    (docs/specs/contract.md). An agent's own run sees its own model instead
    (`ClassSchema.parse_input`).
    """

    model_config = ConfigDict(frozen=True, extra="allow")
    schema_class: str


def _open_input(value: Any) -> Any:
    return OpenInput.model_validate(value) if isinstance(value, dict) else value


# Any input: an agent's own model, or an `OpenInput`. Serialised as the instance it holds.
AnyInputDocument = Annotated[SerializeAsAny[Frozen], BeforeValidator(_open_input)]


class InvocationRequest(Frozen):
    invocation_id: str = Field(default_factory=new_invocation_id, pattern=UUID7_PATTERN)
    agent_id: str
    requirement_ids: list[str] = Field(default_factory=list)
    issued_at: datetime = Field(default_factory=now)
    conversation_id: str | None = Field(default=None, pattern=UUID7_PATTERN)
    # Set only by the conductor, from the conversation or a delegation grant, and never sent to
    # the agent (docs/specs/projects.md).
    project_id: str | None = Field(default=None, pattern=UUID7_PATTERN)
    # Set only by the conductor, from a delegation grant (docs/specs/orchestration.md).
    parent_invocation_id: str | None = Field(default=None, pattern=UUID7_PATTERN)
    input: AnyInputDocument


# --- Outcome and problems -------------------------------------------------------------------


class Outcome(Frozen):
    status: OutcomeStatus
    reason_code: ReasonCode | None = None
    referred_to: str | None = None
    statement: str


class ProblemDetails(Frozen):
    type: str
    title: str | None = None
    http_status: int | None = None
    detail: str | None = None
    instance: str | None = None
    resume_condition: str | None = None
    resume_after: datetime | None = None


# --- Grounding ------------------------------------------------------------------------------


class GroundingRef(Frozen):
    """Identity and content hash of one retrieved thing a payload rests on
    (docs/specs/grounding.md)."""

    source_id: str
    content_hash: str = Field(pattern=SHA256_PATTERN)


class Grounded(Frozen):
    """Mixin: every payload class and every identity-asserting item carries `grounded_on`."""

    grounded_on: list[GroundingRef] = Field(default_factory=list)


def input_source_id(invocation_id: str) -> str:
    """The `source_id` an input_only or none agent cites for the input it was given."""
    return f"input:{invocation_id}"


def invocation_source_id(invocation_id: str) -> str:
    """The `source_id` a delegation agent cites for a child envelope it relays
    (docs/specs/orchestration.md)."""
    return f"invocation:{invocation_id}"


class OpenPayload(Grounded):
    """A payload held as the document it is, checked against its class schema
    (docs/specs/contract.md)."""

    model_config = ConfigDict(frozen=True, extra="allow")
    schema_class: str


def _open_payload(value: Any) -> Any:
    return OpenPayload.model_validate(value) if isinstance(value, dict) else value


# Any payload: an agent's own model, or an `OpenPayload`. Serialised as the instance it holds.
AnyPayloadDocument = Annotated[SerializeAsAny[Grounded], BeforeValidator(_open_payload)]


# --- Payloads -------------------------------------------------------------------------------
# Every payload class carries `schema_class` and mixes in Grounded. The core defines only the
# conversation's Reply and the project's Document; every other payload class belongs to its agent
# (docs/specs/contract.md, docs/specs/projects.md).


class ChoiceOption(Frozen):
    """One option of a choice question. The value is a string: a number would reach the agent as
    a floating-point value over A2A."""

    option_value: str
    option_label: str
    option_help: str | None = None


class Question(Frozen):
    """One question a reply asks, shown as a form field. A choice question has fixed options, of
    which one or several may be chosen, and may be answered in the researcher's own words where
    `question_other` is true; a short or long text question is answered in their own words and
    has no options."""

    question_key: str = Field(pattern=QUESTION_KEY_PATTERN)
    question_prompt: str
    question_kind: QuestionKind
    question_help: str | None = None
    # The bounds are not in the schema (#333).
    question_options: list[ChoiceOption] | None = Field(
        default=None, min_length=CHOICE_OPTIONS_MIN, max_length=CHOICE_OPTIONS_MAX
    )
    question_multiple: bool = False
    question_other: bool = False

    @model_validator(mode="after")
    def _options_fit_the_kind(self) -> Question:
        if self.question_kind is QuestionKind.CHOICE:
            if self.question_options is None:
                raise ValueError("a choice question has options")
            values = [o.option_value for o in self.question_options]
            if len(set(values)) != len(values):
                raise ValueError("each option of a choice question has a value of its own")
        elif self.question_options is not None or self.question_multiple or self.question_other:
            raise ValueError("only a choice question has options")
        return self


class Reply(Grounded):
    """The payload of a conversational agent (docs/specs/orchestration.md)."""

    schema_class: Literal["Reply"] = "Reply"
    reply_text: str
    reply_derivation: Derivation
    # Set by a model on a conversation's first turn only; what lists the conversation shows.
    conversation_title: str | None = Field(default=None, pattern=CONVERSATION_TITLE_PATTERN)
    # The questions the reply asks, put to the researcher one at a time and answered together.
    # The bounds are not in the schema (#333).
    reply_questions: list[Question] | None = Field(
        default=None, min_length=1, max_length=QUESTIONS_MAX
    )
    # A name for the conversation's project, which the conductor records unless a person named it.
    new_project_title: str | None = Field(default=None, pattern=NEW_PROJECT_TITLE_PATTERN)
    # An entry point a model worked out, which the conductor records unless the researcher chose
    # one. The bounds are not in the schema (#333).
    new_project_entry: int | None = Field(default=None, ge=1, le=3)

    @model_validator(mode="after")
    def _question_keys_are_unique(self) -> Reply:
        keys = [q.question_key for q in self.reply_questions or []]
        if len(set(keys)) != len(keys):
            raise ValueError("each question of a reply has a key of its own")
        return self


class DocumentVersionRef(Frozen):
    """One version of a project document, numbered from 1 within it (docs/specs/projects.md)."""

    document_id: str = Field(pattern=UUID7_PATTERN)
    version: int = Field(ge=1)  # not in the schema (#333)


class DocumentQuestion(Frozen):
    """A drafter's question about one gap in its draft: a README section, or a data dictionary
    cell named by file, field and column (docs/specs/drafting.md)."""

    question_id: str = Field(pattern=QUESTION_ID_PATTERN)
    question_prompt: str
    gap_section: str | None = None
    # The part of the section, when the drafter asks a section part by part.
    gap_part: str | None = None
    gap_file: str | None = None
    gap_field: str | None = None
    gap_column: str | None = None
    # Offered with the question, never placed in the document (docs/specs/drafting.md).
    suggested_answer: str | None = None
    suggestion_derivation: Derivation | None = None

    @model_validator(mode="after")
    def _one_target(self) -> DocumentQuestion:
        if (self.suggested_answer is None) != (self.suggestion_derivation is None):
            raise ValueError("a suggested answer says how it was derived, and only then")
        cell = (self.gap_file, self.gap_field, self.gap_column)
        if self.gap_part is not None and self.gap_section is None:
            raise ValueError("a question targets a part only within a README section")
        if self.gap_section is not None:
            if any(c is not None for c in cell):
                raise ValueError("a question targets a README section or a cell, not both")
        elif any(c is None for c in cell):
            raise ValueError(
                "a question targets a README section, or a cell by file, field and column"
            )
        return self


class Document(Grounded):
    """A project document an agent drafts or regenerates, as text (docs/specs/projects.md)."""

    schema_class: Literal["Document"] = "Document"
    document_kind: DocumentKind
    document_title: str | None = None
    media_type: str
    conforms_to: str | None = None
    document_text: str
    document_derivation: Derivation
    revises: DocumentVersionRef | None = None
    # One question for each gap the version leaves (docs/specs/drafting.md).
    document_questions: list[DocumentQuestion] = Field(default_factory=list)

    @model_validator(mode="after")
    def _question_ids_are_unique(self) -> Document:
        ids = [q.question_id for q in self.document_questions]
        if len(set(ids)) != len(ids):
            raise ValueError("each question of a document has an identifier of its own")
        return self


# --- Drafting ---------------------------------------------------------------------------------
# The input every drafter accepts (docs/specs/projects.md). A core input class, like
# Message, so that one drafter can replace another without its caller changing.


class CurrentVersion(Frozen):
    """The version of a project document a drafter is to regenerate, with any decision on it."""

    version_ref: DocumentVersionRef
    document_title: str | None = None
    media_type: str
    document_text: str
    version_state: VersionState
    decision_reason: str | None = None


class ApprovedMetadataRecord(Frozen):
    """The version of the project's metadata record a person approved last
    (docs/specs/projects.md)."""

    version_ref: DocumentVersionRef
    media_type: str
    conforms_to: str | None = None
    document_text: str


class DraftAnswer(Frozen):
    """A person's answer to one of the current version's questions, placed as given."""

    answered_question: str = Field(pattern=QUESTION_ID_PATTERN)
    answer_text: str


class DraftRequest(Frozen):
    """A project document of one kind to draft from the project's facts (docs/specs/projects.md)."""

    schema_class: Literal["DraftRequest"] = "DraftRequest"
    document_kind: DocumentKind
    inventory: FileInventory | None = None
    requirements: RepositoryRequirements | None = None
    metadata_record: ApprovedMetadataRecord | None = None
    current_version: CurrentVersion | None = None
    # Filled by the conductor in a project, from the answers people recorded.
    draft_answers: list[DraftAnswer] = Field(default_factory=list)
    # The project document to redraft, where the project holds more than one of the kind.
    redraft_document: str | None = Field(default=None, pattern=UUID7_PATTERN)
    # Filled by the conductor in a project, from the facts people kept from their ORCID records.
    researchers: list[ResearcherRecord] = Field(default_factory=list)


# --- Evidence and telemetry -----------------------------------------------------------------


class EvidenceItem(Frozen):
    source_id: str
    source_uri: str | None = None
    retrieved_at: datetime | None = None
    snapshot_ref: str | None = None
    hash_algorithm: str = "sha256"
    canonicalisation: str
    content_hash: str = Field(pattern=SHA256_PATTERN)
    # What the hash covers, already projected; the linter re-hashes it (E1,
    # docs/specs/grounding.md).
    content: dict[str, Any] | None = None


class ModelCall(Frozen):
    """One call an agent made to a language model, as it reports it (docs/specs/disclosure.md).
    `prompt_digest` names the messages sent; the harness keeps them beside the run.
    `model_account` says whose account paid, never whose key; it is absent only in runs recorded
    before contract 0.10.0."""

    model_provider: str
    model_id: str
    called_at: datetime
    prompt_digest: str = Field(pattern=SHA256_PATTERN)
    input_tokens: int | None = None
    output_tokens: int | None = None
    model_account: ModelAccount | None = None


class Telemetry(Frozen):
    trace_id: str | None = None
    model_id: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    energy_estimate_j: float | None = None
    energy_method: EnergyMethod = EnergyMethod.NOT_MEASURED
    model_calls: list[ModelCall] = Field(default_factory=list)


# --- Envelope -------------------------------------------------------------------------------


class Delegation(Frozen):
    """One child invocation, as the conductor recorded it (docs/specs/orchestration.md)."""

    delegated_invocation_id: str = Field(pattern=UUID7_PATTERN)
    delegated_agent_id: str
    delegated_agent_version: str
    delegated_status: OutcomeStatus
    content_hash: str = Field(pattern=SHA256_PATTERN)


class Principal(Frozen):
    """The human an invocation acted for (Blueprint §5.4, docs/specs/policy-and-identity.md)."""

    principal_id: str = Field(pattern=IRI_PATTERN)
    name: str = Field(pattern=r"\S")
    principal_kind: PrincipalKind = PrincipalKind.PERSON
    assurance: Assurance = Assurance.ASSERTED
    # The issuer that vouched: required when authenticated, absent when asserted
    # (docs/specs/policy-and-identity.md).
    vouched_by: str | None = Field(default=None, pattern=IRI_PATTERN)

    @model_validator(mode="after")
    def _vouched_by_matches_assurance(self) -> Principal:
        if self.assurance == Assurance.AUTHENTICATED and self.vouched_by is None:
            raise ValueError(
                "an authenticated principal names the issuer that vouched (vouched_by)"
            )
        if self.assurance == Assurance.ASSERTED and self.vouched_by is not None:
            raise ValueError("an asserted principal was vouched for by nobody: omit vouched_by")
        return self


class Envelope(Frozen):
    invocation_id: str = Field(pattern=UUID7_PATTERN)
    agent_id: str
    agent_version: str
    completed_at: datetime
    grounding_mode: GroundingMode
    # The profile the conductor applied; the deployment's, never the request's
    # (docs/specs/policy-and-identity.md).
    policy_bundle_ref: str = Field(pattern=POLICY_BUNDLE_REF_PATTERN)
    policy_digest: str = Field(pattern=SHA256_PATTERN)
    # Named by the authentication boundary, never by the request
    # (docs/specs/policy-and-identity.md).
    acting_for: Principal
    # The core contract, and the class schemas the card carried, that the run was checked
    # against (docs/specs/contract.md). The digests name schemas the run store keeps.
    contract_version: str = Field(pattern=VERSION_PATTERN)
    input_schema: str | None = Field(default=None, pattern=SHA256_PATTERN)
    outcome: Outcome
    payload: AnyPayloadDocument | None = None
    payload_schema: str | None = Field(default=None, pattern=SHA256_PATTERN)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    telemetry: Telemetry
    requires_human_review: Literal[True] = True
    problem: ProblemDetails | None = None
    conversation_id: str | None = Field(default=None, pattern=UUID7_PATTERN)
    # The project the run belongs to, filled by the conductor (docs/specs/projects.md).
    project_id: str | None = Field(default=None, pattern=UUID7_PATTERN)
    parent_invocation_id: str | None = Field(default=None, pattern=UUID7_PATTERN)
    delegations: list[Delegation] = Field(default_factory=list)

    def payload_as[P: Grounded](self, model: type[P]) -> P:
        """The payload as `model`, the reader's own model of its class (docs/specs/contract.md).

        The harness holds a payload as an `OpenPayload`; a reader that knows the class, such as
        the agent's own tests or an orchestrator relaying a child, parses it here. Raises
        `ValueError` if there is no payload or it is not of `model`'s class.
        """
        if self.payload is None:
            raise ValueError(f"envelope {self.invocation_id} carries no payload")
        if isinstance(self.payload, model):
            return self.payload
        return model.model_validate(to_document(self.payload))

    def to_document(self) -> dict[str, Any]:
        """JSON-ready dict in the shape the generated schema validates.

        Optional slots are omitted rather than emitted as null (enum-ranged slots are not
        nullable in the generated schema). The one exception is `energy_estimate_j`, which is
        written as an explicit null: P14 asks for the footprint to be captured, and an explicit
        null says "slot exists, not measured" where an absent key says nothing. An empty
        `delegations` or `model_calls` list is omitted, so envelopes of agents that neither
        delegate nor call a model are unchanged.
        """
        doc = to_document(self)
        doc["telemetry"].setdefault("energy_estimate_j", None)
        if not doc["telemetry"]["model_calls"]:
            # Only a run that called a model lists its calls (docs/specs/disclosure.md).
            del doc["telemetry"]["model_calls"]
        if not doc["delegations"]:
            # Only a delegation agent's envelope lists them (docs/specs/orchestration.md).
            del doc["delegations"]
        return doc


def to_document(model: BaseModel) -> dict[str, Any]:
    return model.model_dump(mode="json", exclude_none=True)
