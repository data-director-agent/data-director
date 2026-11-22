/**
 * The bodies the app's routes answer with, as TypeScript (docs/specs/app.md, "API types").
 *
 * Generated from the app's response models (app/src/dd_app/responses.py) by
 * app/web/scripts/gen-api-types.mjs. Do not edit: change the models and run, in app/web,
 *
 *     npm run gen:api
 *
 * CI fails when this file is not what the models generate.
 */

import type { Question } from "../../conversation/question";
import type { ProjectFact } from "../../project/facts";
import type { ResearcherRecord } from "../../project/researcher";
import type { DocumentQuestion, DocumentVersionRef, InvocationRequest, Principal } from "../contract";
import type { Envelope, RawModelUse, RawSchemaEntry, RawSkillUse, RawToolUse } from "@data-director/agent-view";

/**
 * Any body the app sends.
 */
export type AppResponse =
  | About
  | AgentSetting
  | AgentsProfile
  | BuiltPackage
  | CheckReport
  | Checks
  | ChecksConfirmed
  | ChosenRepository
  | ConfirmationStatement
  | Conversation
  | ConversationDeleted
  | ConversationSummary
  | ConversationTurn
  | Decision
  | DeletedConversation
  | DeletedProject
  | DeployedProfile
  | DepositConnection
  | DepositRefusedProblem
  | DepositReview
  | DepositShown
  | Deposits
  | Derivation
  | DisclosedDocument
  | DisclosedDraft
  | DisclosedModel
  | Disclosure
  | DocumentCheck
  | DocumentCounts
  | DocumentDraftedBy
  | DocumentFinding
  | DocumentVersion
  | Escalation
  | EscalationMove
  | EscalationOrigin
  | EscalationState
  | Example
  | ExtractedDocument
  | FactProposal
  | FiledIssue
  | FlowEntry
  | FlowPhase
  | FlowStep
  | FolderListing
  | HistoryEntry
  | IntakeQuestion
  | IntakeState
  | ItemDecisionMade
  | MoveName
  | OriginKind
  | OutcomeStatus
  | PackageLink
  | PackageRefusedProblem
  | Policy
  | PolicyAgent
  | PolicyProfile
  | PolicyStep
  | PrincipalSummary
  | ProblemDetails
  | ProcessFlow
  | ProjectConversation
  | ProjectDeletion
  | ProjectDetails
  | ProjectDocument
  | ProjectDocuments
  | ProjectEscalations
  | ProjectFacts
  | ProjectIntake
  | ProjectMember
  | ProjectMembers
  | ProjectProgress
  | ProjectRuns
  | ProjectSummary
  | QueuedEscalation
  | RawAgentsResponse
  | RawManifestEntry
  | RawModelAccountProvider
  | RawSession
  | RawSessionPrincipal
  | RawStewardTeam
  | ReasonRequired
  | RecordedAnswer
  | RepositoryMatch
  | RepositorySearch
  | RepositoryTicket
  | ReviewItem
  | ReviewRules
  | RevisionRequested
  | RevisionRun
  | Role
  | RunResult
  | RunRow
  | SavedInventory
  | ServerFolderRoots
  | Started
  | StepReason
  | StepState
  | StewardQueue
  | StoredRun
  | SupportTeamOption
  | Ticket
  | Validation
  | ValidationResult
  | VersionChange
  | VersionDecision;
export type StepState = "started" | "done" | "skipped";
export type OutcomeStatus = "succeeded" | "abstained" | "referred" | "failed" | "suspended";
export type MoveName = "open" | "take" | "release" | "wait" | "reply" | "resolve" | "hand_back" | "withdraw" | "reopen";
export type OriginKind = "researcher" | "policy_gate" | "agent" | "orchestrator";
export type EscalationState = "open" | "taken" | "waiting_for_researcher" | "resolved" | "handed_back" | "withdrawn";
export type IntakeState = "pending" | "complete" | "dismissed";
export type Role = "owner" | "member";

/**
 * The build, what the deployment runs and what it offers (`GET /api/about`, open to all).
 */
export interface About {
  app_version: string | null;
  commit: string | null;
  feedback_enabled: boolean;
  harness_version: string | null;
  /**
   * The configured agents built against another contract, by name.
   */
  incompatible: string[];
  /**
   * The operator's privacy notice for this instance, or null if it has set none.
   */
  privacy_notice_url: string | null;
  profile: DeployedProfile;
  /**
   * Whether it may describe folders on its own machine (`dd_app.folder_scan`).
   */
  server_folders: boolean;
  /**
   * The configured agents it cannot reach, by name.
   */
  unavailable: string[];
}
export interface DeployedProfile {
  digest: string;
  id: string;
  orchestrator: string | null;
  version: number;
}
/**
 * An option a deployment's profile may set for an agent.
 */
export interface AgentSetting {
  choices: string[];
  default: string;
  description: string;
}
export interface AgentsProfile {
  /**
   * Whether the profile lets people attach documents to a turn.
   */
  attached_documents: "allowed" | "refused";
  digest: string;
  /**
   * The agent the profile names for the conversation; null when it names none.
   */
  orchestrator: string | null;
  ref: string;
}
/**
 * The validation that let the package be built, and the package.
 */
export interface BuiltPackage {
  conforms: boolean;
  /**
   * Information that never blocks, such as what the repository fills in itself.
   */
  infos: ValidationResult[];
  package: PackageLink;
  project_id: string;
  /**
   * Whether a package may be built: no violation, and nothing waits on a person.
   */
  ready: boolean;
  /**
   * The W3C SHACL Validation Report, in JSON-LD.
   */
  report: {
    [k: string]: unknown;
  };
  report_digest: string | null;
  requirements_digest: string | null;
  /**
   * What a person must decide and confirm; null when no repository has been chosen.
   */
  review: DepositReview | null;
  validated_at: string;
  violations: ValidationResult[];
  /**
   * Warnings that do not wait on a person; those that do are the `review`'s.
   */
  warnings: ValidationResult[];
}
/**
 * One result of a validation: what is missing, in the harness's words.
 */
export interface ValidationResult {
  /**
   * The check that made it.
   */
  component: string;
  /**
   * The field or document it is about, such as the repository's form label, or null.
   */
  field: string | null;
  /**
   * The node the result is about, such as the project or the metadata record.
   */
  focus: string;
  message: string;
  path: string | null;
  /**
   * The project's page where a person supplies what is missing, or null.
   */
  supplied_on: ("documents" | "researchers" | "facts" | "repository") | null;
}
/**
 * A deposit package the harness built, kept by the SHA-256 of its bytes.
 */
export interface PackageLink {
  digest: string;
  /**
   * Where to download it, as a zip.
   */
  href: string;
  /**
   * In bytes.
   */
  size: number;
}
/**
 * What a person must decide and confirm before the project is packaged. No item means that
 * nothing was flagged in what was checked, never that the data are safe: `not_checked` says
 * what was not.
 */
export interface DepositReview {
  /**
   * The confirmation that stands for the current inventory, or null.
   */
  confirmation: ChecksConfirmed | null;
  inventory_digest: string | null;
  items: ReviewItem[];
  not_checked: string[];
  /**
   * What the confirmation states, each of which must be confirmed.
   */
  statements: ConfirmationStatement[];
}
/**
 * A person's confirmation of the checks before deposit, against the current inventory.
 */
export interface ChecksConfirmed {
  confirmed_at: string;
  confirmed_by: Principal;
  statements: ConfirmationStatement[];
}
/**
 * One statement a person confirms before a deposit.
 */
export interface ConfirmationStatement {
  id: string;
  text: string;
}
/**
 * A file a person must decide about before packaging, and why: a name-level hint or a
 * personal-data finding from the inventory.
 */
export interface ReviewItem {
  column: string | null;
  /**
   * The decision that stands for this item, or null while it waits on a person.
   */
  decision: ItemDecisionMade | null;
  file_sha256: string | null;
  item_id: string;
  kind: string;
  matched: string | null;
  path: string;
  /**
   * What the person should check, in the harness's words.
   */
  question: string;
  related_paths: string[];
  source: "name" | "finding";
}
/**
 * The decision a person made on an item, and who made it when.
 */
export interface ItemDecisionMade {
  decided_at: string;
  decided_by: Principal;
  decision: "keep" | "leave_out" | "change";
  note: string | null;
}
/**
 * A check's stored summary.
 */
export interface CheckReport {
  passed: boolean;
  summary: string;
}
/**
 * What the grounding linter and the source check reported; null where a run has none.
 */
export interface Checks {
  grounding: CheckReport | null;
  sources: CheckReport | null;
}
/**
 * The repository a project chose last, as its summary names it.
 */
export interface ChosenRepository {
  chosen_at: string;
  re3data_id: string | null;
  /**
   * Its re3data identifier, or, for one re3data does not list, its DataCite one.
   */
  repository_id: string;
  repository_name: string;
  /**
   * What the choice does not check, for example that re3data does not list DataCite for it.
   */
  warnings: string[];
}
/**
 * A conversation as the harness derives it from the run store
 * (`GET /api/conversations/{id}`).
 */
export interface Conversation {
  conversation_id: string;
  history: HistoryEntry[];
  /**
   * Every stored input, the delegated runs' too, by `invocation_id`.
   */
  inputs: {
    [k: string]: {
      [k: string]: unknown;
    } | null;
  };
  /**
   * The inventory the project holds now; absent where the server keeps no projects.
   */
  inventory?: SavedInventory | null;
  /**
   * Where the project is in the process flow now; absent where the server keeps no
   * projects.
   */
  progress?: ProjectProgress;
  /**
   * The project it was started in; absent for one started, with no turn, where the server
   * keeps no projects.
   */
  project_id?: string | null;
  turns: ConversationTurn[];
  version_changes: VersionChange[];
}
/**
 * One entry of the conversation so far, as a turn's `Message.history` gives it.
 */
export interface HistoryEntry {
  role: "user" | "agent";
  turn_agent_id?: string;
  turn_agent_version?: string;
  turn_invocation_id?: string;
  turn_text: string;
}
/**
 * What a project holds of the inventory added last.
 */
export interface SavedInventory {
  added_at: string;
  digest: string;
  file_count: number;
  inventory_made_at: string;
  /**
   * How many folders it is made of, when it is made of parts, or null.
   */
  part_count: number | null;
  /**
   * The digest of the inventory it replaced, or null.
   */
  revises: string | null;
}
/**
 * Where a project is in the process flow, derived from its log on every read
 * (`dd_harness.progress.describe`): the entry point, each step started, done or skipped, and
 * the step to suggest next, which is never a gate.
 */
export interface ProjectProgress {
  decisions: Decision[];
  entry: number | null;
  /**
   * Who recorded the entry point: the researcher, or Data Director from what they said.
   */
  entry_source: ("researcher" | "model") | null;
  /**
   * Why each step in `steps` is in its state, keyed the same.
   */
  reasons: {
    [k: string]: StepReason;
  };
  steps: {
    [k: string]: StepState;
  };
  suggested: string | null;
}
/**
 * One of the intake's decision points (Blueprint §8's diamonds) with its current answer.
 */
export interface Decision {
  answer_labels: string[] | null;
  answer_values: string[] | null;
  /**
   * Whether it is asked from the project's entry point.
   */
  asked: boolean;
  /**
   * The step the decision sits before.
   */
  before: string;
  prompt: string;
  question_id: string;
}
/**
 * What decided a step's state: the log's work (`produced`), the researcher's mark
 * (`marked`), or an intake answer that skipped it (`intake`).
 */
export interface StepReason {
  /**
   * When the deciding event was recorded, where the log says.
   */
  at?: string;
  /**
   * The document whose work decided a document step.
   */
  document_id?: string;
  document_kind?: string;
  /**
   * The kind of the deciding event.
   */
  event: string;
  /**
   * The intake question whose answer skipped the step.
   */
  question_id?: string;
  source: "produced" | "marked" | "intake";
  state: StepState;
}
export interface ConversationTurn {
  agent_id: string;
  agent_version: string;
  /**
   * The runs it delegated to, in the order stored.
   */
  children: Envelope[];
  completed_at: string;
  envelope: Envelope;
  /**
   * The turn's input as stored; null if its request was not stored.
   */
  input: {
    [k: string]: unknown;
  } | null;
  invocation_id: string;
  status: OutcomeStatus;
  turn_index: number;
}
/**
 * Where an agent's version differs from its version earlier in the conversation.
 */
export interface VersionChange {
  agent_id: string;
  /**
   * The version it had before.
   */
  from: string;
  to: string;
  turn_index: number;
}
/**
 * A conversation deleted, and until when it may be restored
 * (`DELETE /api/conversations/{id}`).
 */
export interface ConversationDeleted {
  /**
   * When it was deleted.
   */
  at: string;
  /**
   * Who deleted it.
   */
  by: Principal;
  conversation_id: string;
  project_id: string;
  restorable_until: string;
}
/**
 * What a list of conversations shows of one (`GET /api/conversations`).
 */
export interface ConversationSummary {
  agent_id: string;
  conversation_id: string;
  first_invocation_id: string;
  last_completed_at: string;
  last_status: OutcomeStatus;
  /**
   * The project it was started in; null where the server keeps no projects.
   */
  project_id: string | null;
  started_at: string;
  /**
   * A model's title from the first turn, or else the start of the first message.
   */
  title: string;
  title_source: "model" | "message";
  turns: number;
}
/**
 * A deleted conversation the person may still restore
 * (`GET /api/conversations/deleted`).
 */
export interface DeletedConversation {
  /**
   * When it was deleted.
   */
  at: string;
  /**
   * Who deleted it.
   */
  by: Principal;
  conversation_id: string;
  project_id: string;
  restorable_until: string;
  /**
   * The `principal_id` of whoever started it, or null if the project does not record it.
   */
  started_by: string | null;
  /**
   * Its title as the harness derives it, or null if it had no turn.
   */
  title: string | null;
}
/**
 * A deleted project, as `GET /api/projects/deleted` lists it and deleting answers.
 */
export interface DeletedProject {
  conversation_count: number;
  created_at: string;
  created_by: Principal;
  /**
   * When it was deleted, by whom, and until when an owner may restore it.
   */
  deleted: ProjectDeletion;
  documents: DocumentCounts;
  /**
   * Whether the project's intake still has a question to ask, has none left, or was
   * dismissed.
   */
  intake: "pending" | "complete" | "dismissed";
  inventory: SavedInventory | null;
  progress: ProjectProgress;
  project_id: string;
  repository: ChosenRepository | null;
  /**
   * For how many days after a deletion an owner may restore the project; 0 makes deletion
   * final.
   */
  restore_days: number;
  /**
   * The project's latest name; null until a person or the Data Director names it.
   */
  title: string | null;
  /**
   * Who gave the name. A person's name is never replaced by the model's.
   */
  title_source: ("researcher" | "model") | null;
}
/**
 * A deletion that stands: nothing is removed, and an owner may restore the project until
 * `restorable_until`.
 */
export interface ProjectDeletion {
  at: string;
  by: Principal;
  restorable_until: string;
}
/**
 * How many of a project's documents have their latest version in each state.
 */
export interface DocumentCounts {
  approved: number;
  proposed: number;
  rejected: number;
}
/**
 * How the project's repository is deposited to: through its API here, when `available`, or
 * by hand, and why not through the API (`unavailable`, a reason code).
 */
export interface DepositConnection {
  available: boolean;
  base_url: string | null;
  repository_name: string;
  /**
   * Whether the API is the platform's test installation, whose items and DOIs are not real.
   */
  sandbox: boolean;
  /**
   * The transport its override names, such as zenodo; null when it names none.
   */
  transport: string | null;
  unavailable: string | null;
}
/**
 * Nothing was approved or sent: `refusal` says why, as a code; `draft_url` names the
 * earlier draft when the package was already deposited.
 */
export interface DepositRefusedProblem {
  detail: string;
  draft_url?: string;
  refusal: string;
  status: number;
  title: string;
  /**
   * The problem's kind: a URI under the deployment's problem base, ending in its slug.
   */
  type: string;
}
/**
 * One deposit a person approved, and its outcome.
 */
export interface DepositShown {
  approved_at: string;
  approved_by: string | null;
  deposit_id?: string;
  /**
   * The RO-Crate package deposited.
   */
  digest: string;
  doi?: string;
  /**
   * Where the draft is in the repository, once it was made.
   */
  draft_url?: string;
  /**
   * Why it failed, as a reason code.
   */
  reason?: string;
  repository_name: string;
  sandbox: boolean;
  state: "pending" | "recorded" | "failed";
  status?: number;
  transport: string;
  /**
   * The metadata record's properties the repository's form had no place for.
   */
  unplaced?: string[];
}
/**
 * Whether the project can be deposited to through an API here, and each deposit approved.
 */
export interface Deposits {
  /**
   * Null when no repository has been chosen.
   */
  connection: DepositConnection | null;
  deposits: DepositShown[];
}
/**
 * How an agent derives one field of its payload.
 */
export interface Derivation {
  how: "template" | "model" | "lexical" | "registry" | "answer";
  recorded_in: string | null;
}
/**
 * One approved version, and how it came about.
 */
export interface DisclosedDocument {
  approved_at: string;
  approved_by: string;
  digest: string;
  document_id: string;
  document_kind: string;
  document_title: string | null;
  draft: DisclosedDraft | null;
  /**
   * People who edited the text after the draft, oldest first, by name.
   */
  edited_by: string[];
  origin: "model" | "model_revised" | "template" | "template_revised" | "person";
  reason: string | null;
  version: number;
}
/**
 * The run that drafted the text a version starts from.
 */
export interface DisclosedDraft {
  agent_id: string;
  agent_version: string;
  completed_at: string | null;
  derivation: string;
  invocation_id: string;
  models: DisclosedModel[];
}
/**
 * One call to a language model, as the drafting run recorded it.
 */
export interface DisclosedModel {
  called_at: string;
  model_id: string;
  prompt_digest: string | null;
  provider: string;
}
/**
 * What a project's approved documents owe to generative AI: the statement, in Markdown, and
 * the same account as a PROV-O graph in JSON-LD.
 */
export interface Disclosure {
  documents: DisclosedDocument[];
  made_at: string;
  /**
   * How many documents await a decision, and so are not disclosed yet.
   */
  pending: number;
  project_id: string;
  prov: {
    [k: string]: unknown;
  };
  statement: string;
}
/**
 * What the check found in a document before it is attached (`POST /api/documentation/check`)
 */
export interface DocumentCheck {
  /**
   * What the check ran.
   */
  checked_with: string;
  findings: DocumentFinding[];
  /**
   * The kinds a researcher confirms: a secret's type stands for itself.
   */
  kinds: string[];
}
/**
 * What may be in a document: a kind of personal data, or `secret` with the type of secret as
 * its detail.
 */
export interface DocumentFinding {
  confidence: string;
  /**
   * The type of secret; left out for personal data.
   */
  detail?: string;
  kind: string;
  /**
   * How many places, as a band, so that a finding cannot be turned into a count.
   */
  places: string;
}
/**
 * The run that drafted a version.
 */
export interface DocumentDraftedBy {
  agent_id: string;
  agent_version: string;
  /**
   * How the drafter made the text, such as `model` or `template`.
   */
  document_derivation: string;
  invocation_id: string;
}
/**
 * One version of a project document, with its text and its state.
 */
export interface DocumentVersion {
  added_at: string;
  added_by: Principal;
  conforms_to: string | null;
  decision: VersionDecision | null;
  /**
   * The SHA-256 of the text as UTF-8, which a decision names as the text shown.
   */
  digest: string;
  document_id: string;
  document_kind: string;
  document_title: string | null;
  /**
   * The run that drafted it; null for a person's edit.
   */
  drafted_by: DocumentDraftedBy | null;
  media_type: string;
  /**
   * What the version asks the researcher, one question per gap.
   */
  questions: DocumentQuestion[];
  revises: DocumentVersionRef | null;
  /**
   * The change a person asked for last to this version, in their words.
   */
  revision_request: RevisionRequested | null;
  /**
   * `questions` for a note that asks what the drafter needs before it writes the document,
   * which cannot be decided on; `draft` for the document itself (docs/specs/drafting.md).
   */
  stage: "questions" | "draft";
  state: "proposed" | "approved" | "rejected";
  text: string;
  version: number;
}
/**
 * A person's decision on a version.
 */
export interface VersionDecision {
  decided_at: string;
  decided_by: Principal;
  reason: string | null;
}
/**
 * A person's request for changes to a version, as the project log records it.
 */
export interface RevisionRequested {
  instruction: string;
  requested_at: string;
  requested_by: Principal;
}
/**
 * A matter handed to a data steward team (docs/specs/stewardship.md, invariant 4).
 */
export interface Escalation {
  escalation_id: string;
  history: EscalationMove[];
  /**
   * The researcher's note when they sent it.
   */
  note: string;
  opened_at: string;
  opened_by: Principal;
  origin: EscalationOrigin;
  /**
   * What the researcher was told would be shared, as they saw it when they confirmed it.
   */
  scope_shared: string[];
  state: EscalationState;
  taken_by: Principal | null;
  team_id: string;
  team_name: string;
  updated_at: string;
}
/**
 * One move in an escalation's history, the opening first.
 */
export interface EscalationMove {
  /**
   * Set for a move a steward made as a steward.
   */
  acting_as?: "steward";
  at: string;
  by: Principal;
  move: MoveName;
  note?: string;
}
/**
 * Where an escalation came from: the researcher, or a run of the project that ended in a
 * referral or an abstention, or the orchestrator's offer.
 */
export interface EscalationOrigin {
  agent_id?: string;
  /**
   * The run it came from; absent for one the researcher raised.
   */
  invocation_id?: string;
  kind: OriginKind;
}
/**
 * An example input the shell offers (`GET /api/examples`).
 */
export interface Example {
  input: {
    [k: string]: unknown;
  };
  name: string;
  /**
   * The class the example names, or null if it names none.
   */
  schema_class: string | null;
}
/**
 * The text read from a Word document or PDF (`POST /api/documentation/extract`).
 */
export interface ExtractedDocument {
  name: string;
  /**
   * The text's length in bytes, as UTF-8.
   */
  size: number;
  text: string;
}
/**
 * A proposal no decision on its kind and subject has followed yet.
 */
export interface FactProposal {
  /**
   * The check agent that proposed it.
   */
  agent_id: string;
  /**
   * The fact as proposed, with why (`proposed_because`), for the person deciding.
   */
  fact: ProjectFact;
  /**
   * The proposal's identifier, which a decision names.
   */
  proposal: string;
  proposed_at: string;
}
/**
 * The GitHub issue a report was filed as (`POST /api/feedback`).
 */
export interface FiledIssue {
  number: number;
  url: string;
}
export interface FlowEntry {
  number: number;
  /**
   * The phase a researcher entering here joins at.
   */
  starts_at: number;
  text: string;
}
export interface FlowPhase {
  /**
   * A short name for the phase in a researcher's words.
   */
  name: string;
  number: number;
  steps: FlowStep[];
  /**
   * One sentence on what the phase is for.
   */
  summary: string;
  /**
   * The Blueprint's title; the shell shows `name`.
   */
  title: string;
}
export interface FlowStep {
  /**
   * A stable label, `<phase>.<step>`, that an agent's `serves` names.
   */
  id: string;
  /**
   * The step in a researcher's words.
   */
  label: string;
  optional: boolean;
  /**
   * The Blueprint has the step but this project does not yet do it.
   */
  out_of_scope: boolean;
  /**
   * A person decides the step (C2); no agent may serve it.
   */
  person_decides: boolean;
  /**
   * How a researcher might open a conversation about the step.
   */
  prompt: string;
  /**
   * The Blueprint requirements applied at this step; empty when the figure names none.
   */
  requirements: string[];
  /**
   * The Blueprint's wording, for the orchestrator; the shell shows `label`.
   */
  text: string;
}
/**
 * The subfolders of `path` under `root`, by name; never a file.
 */
export interface FolderListing {
  folders: string[];
  path: string;
  root: string;
}
/**
 * One intake question asked from the project's entry point, with its current answer.
 */
export interface IntakeQuestion {
  /**
   * The values of the latest answer, or null while it has none.
   */
  answer_values: string[] | null;
  /**
   * What an answer says to the researcher at once, by answer value; only for those that do.
   */
  notices?: {
    [k: string]: string;
  };
  /**
   * The question as the contract's `Question` has it.
   */
  question: Question;
  /**
   * The intake's stable id, `intake.<name>`, which an answer is posted to.
   */
  question_id: string;
}
/**
 * No package was built because the project is not valid: `validation` says why.
 */
export interface PackageRefusedProblem {
  detail: string;
  status: number;
  title: string;
  /**
   * The problem's kind: a URI under the deployment's problem base, ending in its slug.
   */
  type: string;
  validation: Validation;
}
/**
 * A project's validation against its chosen repository's requirements, as the harness made
 * it and kept it in the project log. A violation stops the package; a warning or information
 * does not; an item undecided or the checks unconfirmed hold it until a person clears them.
 */
export interface Validation {
  conforms: boolean;
  /**
   * Information that never blocks, such as what the repository fills in itself.
   */
  infos: ValidationResult[];
  project_id: string;
  /**
   * Whether a package may be built: no violation, and nothing waits on a person.
   */
  ready: boolean;
  /**
   * The W3C SHACL Validation Report, in JSON-LD.
   */
  report: {
    [k: string]: unknown;
  };
  report_digest: string | null;
  requirements_digest: string | null;
  /**
   * What a person must decide and confirm; null when no repository has been chosen.
   */
  review: DepositReview | null;
  validated_at: string;
  violations: ValidationResult[];
  /**
   * Warnings that do not wait on a person; those that do are the `review`'s.
   */
  warnings: ValidationResult[];
}
/**
 * The rules the policy gate holds every run to (`GET /api/policy`).
 */
export interface Policy {
  actions_requiring_approval: string[];
  agents: PolicyAgent[];
  profile: PolicyProfile;
  /**
   * Each Blueprint step in order, with how far it is delegated here.
   */
  steps: PolicyStep[];
}
export interface PolicyAgent {
  /**
   * The action class the profile assigns the agent.
   */
  action_class: string;
  agent_id: string;
  requires_approval: boolean;
}
export interface PolicyProfile {
  description: string;
  /**
   * SHA-256 of the profile file's bytes.
   */
  digest: string;
  id: string;
  /**
   * The agent a conversation goes to; null when the profile names none.
   */
  orchestrator: string | null;
  /**
   * What every stored run records as the rules it was held to.
   */
  ref: string;
  version: number;
}
/**
 * How far a Blueprint step is delegated under this profile (#448).
 *
 * Worked out from the profile and the agents serving the step, not set by a profile key.
 */
export interface PolicyStep {
  /**
   * The classes the profile assigns those agents.
   */
  action_classes: string[];
  /**
   * The enabled agents serving the step.
   */
  agent_ids: string[];
  /**
   * `delegated`: the agents serving it run as their class allows; `must_approve`: a serving
   * agent's class needs approval, so its runs are referred; `never_delegated`: a person decides it;
   * `not_offered`: no agent here does it.
   */
  autonomy: "delegated" | "must_approve" | "never_delegated" | "not_offered";
  /**
   * The step in a researcher's words.
   */
  label: string;
  phase_name: string;
  phase_number: number;
  /**
   * Why a step is not offered; null for any other.
   */
  reason: ("out_of_scope" | "no_agent") | null;
  /**
   * Whom the step's runs are referred to, such as `data_steward`; null when none.
   */
  refers_to: string | null;
  step_id: string;
}
/**
 * What the shell is told about a person (`dd_app.governance.principal_summary`): whom runs
 * act for, and who vouched for them.
 */
export interface PrincipalSummary {
  assurance: "asserted" | "authenticated";
  name: string;
  /**
   * The issuer that vouched for an authenticated person; absent for an asserted one.
   */
  vouched_by?: string;
}
/**
 * An RFC 9457 problem, which every refusal and failure is answered with.
 *
 * Open, as RFC 9457 lets a problem carry extension members; a problem whose members are known
 * is described by a subclass that names them (and closes it again with `extra="forbid"`).
 */
export interface ProblemDetails {
  detail: string;
  status: number;
  title: string;
  /**
   * The problem's kind: a URI under the deployment's problem base, ending in its slug.
   */
  type: string;
  [k: string]: unknown;
}
/**
 * The Blueprint's entry points and phases (`GET /api/process-flow`, `dd_sdk.process_flow`).
 */
export interface ProcessFlow {
  entries: FlowEntry[];
  phases: FlowPhase[];
}
/**
 * A conversation started in a project, as the projects list names it.
 */
export interface ProjectConversation {
  conversation_id: string;
  /**
   * When its latest turn completed; null while none has.
   */
  last_completed_at: string | null;
  started_at: string;
  title: string;
  turns: number;
}
/**
 * One project as the project log gives it: what it holds, how many of its documents are in
 * each state, where it is in the process flow and whether it is deleted. Renaming and restoring
 * a project answer with it.
 */
export interface ProjectDetails {
  conversation_count: number;
  created_at: string;
  created_by: Principal;
  /**
   * When the project was deleted, by whom, and until when an owner may restore it; null
   * while it is not deleted.
   */
  deleted: ProjectDeletion | null;
  documents: DocumentCounts;
  /**
   * Whether the project's intake still has a question to ask, has none left, or was
   * dismissed.
   */
  intake: "pending" | "complete" | "dismissed";
  inventory: SavedInventory | null;
  progress: ProjectProgress;
  project_id: string;
  repository: ChosenRepository | null;
  /**
   * For how many days after a deletion an owner may restore the project; 0 makes deletion
   * final.
   */
  restore_days: number;
  /**
   * The project's latest name; null until a person or the Data Director names it.
   */
  title: string | null;
  /**
   * Who gave the name. A person's name is never replaced by the model's.
   */
  title_source: ("researcher" | "model") | null;
}
/**
 * One of a project's documents, with every version oldest first.
 */
export interface ProjectDocument {
  /**
   * The answers given to its questions, which the next draft places as supplied.
   */
  answers: RecordedAnswer[];
  document_id: string;
  document_kind: string;
  document_title: string | null;
  versions: DocumentVersion[];
}
/**
 * A person's answer to one question, as the project log records it: the latest stands.
 */
export interface RecordedAnswer {
  answer_text: string;
  answered_at: string;
  answered_by: Principal;
  question_id: string;
  /**
   * The version whose question it answered.
   */
  version: number;
}
/**
 * A project's documents and the rules a decision or answer form states.
 */
export interface ProjectDocuments {
  /**
   * The longest answer the harness keeps, in characters.
   */
  answer_max_length: number;
  /**
   * After answers: the version whose questions they answered.
   */
  answered?: DocumentVersionRef;
  /**
   * After a decision: the version it decided.
   */
  decided?: DocumentVersionRef;
  documents: ProjectDocument[];
  project_id: string;
  /**
   * The longest request for changes the harness keeps, in characters.
   */
  request_max_length: number;
  review: ReviewRules;
  /**
   * After a request for changes: the run that revised the document, or declined to.
   */
  revised?: RevisionRun;
}
/**
 * The harness's rule for when a decision needs a reason, which the form states.
 */
export interface ReviewRules {
  reason_max_length: number;
  reason_required: ReasonRequired;
}
/**
 * Whether each kind of decision needs a reason.
 */
export interface ReasonRequired {
  approved: boolean;
  edited_and_approved: boolean;
  rejected: boolean;
}
/**
 * The run asked to revise a document: its outcome, and the version it drafted, if any.
 */
export interface RevisionRun {
  invocation_id: string;
  statement: string;
  status: "succeeded" | "abstained" | "referred" | "failed";
  version: DocumentVersionRef | null;
}
/**
 * A project's escalations, the teams it may send to, and where a new one would go.
 */
export interface ProjectEscalations {
  escalations: Escalation[];
  /**
   * The team a new escalation would go to without a pick, or null with `unrouted` saying why.
   */
  routes_to: string | null;
  /**
   * The team the project's owners chose, or null.
   */
  support_team: string | null;
  teams: SupportTeamOption[];
  unrouted: ("no-steward-team" | "team-required") | null;
}
/**
 * A steward team the deployment names, which a project may choose as its support team.
 */
export interface SupportTeamOption {
  contact?: string;
  name: string;
  response_time?: string;
  /**
   * The labels of the projects the team supports.
   */
  supports: string[];
  team_id: string;
}
/**
 * What a project holds: proposals to decide, and the facts that stand.
 */
export interface ProjectFacts {
  /**
   * After a decision, the fact that now stands, or null after a rejection.
   */
  decided?: ProjectFact | null;
  /**
   * The facts that stand: the last decision on each kind and subject.
   */
  decisions: ProjectFact[];
  proposals: FactProposal[];
}
/**
 * Where a project's intake stands (`dd_harness.intake.describe`): the next question, every
 * question asked from the entry point with its answer, and the project's progress.
 */
export interface ProjectIntake {
  next: string | null;
  progress: ProjectProgress;
  questions: IntakeQuestion[];
  state: IntakeState;
}
/**
 * One member of a project.
 */
export interface ProjectMember {
  /**
   * Whether this member is the person asking.
   */
  is_you: boolean;
  /**
   * The identifier the member signs in with, such as their ORCID iD as a URL.
   */
  member_id: string;
  /**
   * When they became a member: the project's creation, for its creator.
   */
  member_since: string;
  /**
   * The name on the member's public ORCID record, read for this answer and never kept; left
   * out where they kept a name, keep theirs private, or ORCID did not answer in time.
   */
  public_name?: string;
  /**
   * The facts the member kept from their own ORCID record, which agents in the project are
   * given; left out while they have kept none.
   */
  record?: ResearcherRecord;
  /**
   * Whether the person asking may remove this member (or leave, for themselves).
   */
  removable: boolean;
  /**
   * The name the member kept from their own ORCID record in this project; left out while they
   * have kept none.
   */
  researcher_name?: string;
  role: Role;
  /**
   * Whether the person asking may change this member's role: an owner, and not of the last
   * owner.
   */
  role_changeable: boolean;
}
/**
 * A project's members, the creator first, and what the person asking may do.
 */
export interface ProjectMembers {
  /**
   * The records kept by people who are no longer members: agents are still given them until
   * their keeper withdraws them.
   */
  former_researchers: ResearcherRecord[];
  /**
   * Whether the person asking may leave: a member, or an owner who is not the last.
   */
  may_leave: boolean;
  /**
   * Whether the person asking may add members and change their roles: an owner.
   */
  may_manage: boolean;
  members: ProjectMember[];
  your_role: Role | null;
}
/**
 * The succeeded runs in a project whose payload is of one class, newest first.
 */
export interface ProjectRuns {
  runs: Envelope[];
}
/**
 * One project the person may read, as `GET /api/projects` lists it and
 * `POST /api/projects` creates it, with the conversations started in it, most recent first.
 */
export interface ProjectSummary {
  conversation_count: number;
  conversations: ProjectConversation[];
  created_at: string;
  created_by: Principal;
  /**
   * When the project was deleted, by whom, and until when an owner may restore it; null
   * while it is not deleted.
   */
  deleted: ProjectDeletion | null;
  documents: DocumentCounts;
  /**
   * Whether the project's intake still has a question to ask, has none left, or was
   * dismissed.
   */
  intake: "pending" | "complete" | "dismissed";
  inventory: SavedInventory | null;
  progress: ProjectProgress;
  project_id: string;
  repository: ChosenRepository | null;
  /**
   * For how many days after a deletion an owner may restore the project; 0 makes deletion
   * final.
   */
  restore_days: number;
  /**
   * The project's latest name; null until a person or the Data Director names it.
   */
  title: string | null;
  /**
   * Who gave the name. A person's name is never replaced by the model's.
   */
  title_source: ("researcher" | "model") | null;
}
/**
 * An escalation routed to one of the steward's teams, with its project.
 */
export interface QueuedEscalation {
  escalation_id: string;
  history: EscalationMove[];
  /**
   * Whether the steward is a member of the project, and so may not act in it as its steward.
   */
  member_of_project: boolean;
  /**
   * The researcher's note when they sent it.
   */
  note: string;
  opened_at: string;
  opened_by: Principal;
  origin: EscalationOrigin;
  project_id: string;
  project_title: string | null;
  /**
   * What the researcher was told would be shared, as they saw it when they confirmed it.
   */
  scope_shared: string[];
  state: EscalationState;
  taken_by: Principal | null;
  team_id: string;
  team_name: string;
  updated_at: string;
}
/**
 * The agents the shell's capabilities panel is drawn from (`GET /api/agents`).
 */
export interface RawAgentsResponse {
  acting_for: PrincipalSummary;
  agents: RawManifestEntry[];
  /**
   * The configured agents built against another contract, by name, with both versions.
   */
  incompatible: {
    [k: string]: string;
  };
  profile: AgentsProfile;
  /**
   * The configured agents it could not reach, by name, with why.
   */
  unavailable: {
    [k: string]: string;
  };
}
/**
 * An agent's manifest, as its card declares it (`dd_sdk.agent.describe`), beside what this
 * deployment's profile assigns it.
 */
export interface RawManifestEntry {
  accepts: string[];
  action_class: string;
  agent_id: string;
  /**
   * The action class the profile assigns it; null if the profile does not list it, and the
   * gate refuses it.
   */
  assigned_action_class: string | null;
  contract_version: string;
  derivations: {
    [k: string]: Derivation;
  };
  description: string;
  grounding_mode: "retrieval" | "input_only" | "none" | "delegation";
  /**
   * The persona's icon, one emoji; empty for none.
   */
  icon: string;
  models: RawModelUse[];
  payload: string | null;
  /**
   * What it reads the text of attached documents for, completing "<title> reads its text …";
   * empty when it does not read them (#1326).
   */
  reads_attached: string;
  requires_approval: boolean;
  schemas: {
    [k: string]: RawSchemaEntry;
  };
  /**
   * The process flow step ids it serves (docs/specs/orchestration.md).
   */
  serves: string[];
  settings: {
    [k: string]: AgentSetting;
  };
  skills: RawSkillUse[];
  /**
   * The persona's name as a researcher sees it; empty for none.
   */
  title: string;
  tools: RawToolUse[];
  version: string;
}
/**
 * A provider a person's own model account may be with.
 */
export interface RawModelAccountProvider {
  /**
   * The origins (`https://host[:port]`) the account may name as its base URL.
   */
  base_urls: string[];
  provider: string;
}
/**
 * Who is signed in, until when, and whether this server signs anyone in
 * (`GET`/`POST /api/session`).
 */
export interface RawSession {
  /**
   * When the session ends if nothing more is done in it (ISO 8601), or null.
   */
  expires_at: string | null;
  /**
   * The identity provider people sign in with (its issuer IRI), or null.
   */
  issuer: string | null;
  /**
   * The providers a person's own account may be with; empty unless `model_accounts`.
   */
  model_account_providers: RawModelAccountProvider[];
  /**
   * Whether a person may add their own model account (docs/specs/model-accounts.md).
   */
  model_accounts: boolean;
  principal: RawSessionPrincipal | null;
  /**
   * Whether a person may connect their own repository account, to deposit a draft through
   * the repository's API (docs/specs/deposit.md).
   */
  repository_accounts: boolean;
  /**
   * False on a development server, where every run acts for the operator.
   */
  signs_in: boolean;
}
/**
 * The person a session is open for.
 */
export interface RawSessionPrincipal {
  assurance: "asserted" | "authenticated";
  name: string;
  principal_id: string;
  /**
   * The person's deployment roles, from the profile (docs/specs/stewardship.md, invariant 1).
   * Everyone is a researcher. No deployment role makes anyone a member of a project.
   */
  roles: ("researcher" | "steward" | "administrator")[];
  /**
   * The steward teams the person is in; empty unless they are a steward.
   */
  teams: RawStewardTeam[];
  /**
   * The issuer that vouched for an authenticated person; absent for an asserted one.
   */
  vouched_by?: string;
}
/**
 * A steward team the person is in, as the profile names it (docs/specs/stewardship.md).
 */
export interface RawStewardTeam {
  name: string;
  team_id: string;
}
/**
 * What a search of the pinned registries shows of one repository.
 */
export interface RepositoryMatch {
  additional_names: string[];
  doi: string | null;
  name: string;
  re3data_id: string | null;
  registry: "re3data" | "datacite";
  /**
   * Its re3data identifier, or, for one re3data does not list, its DataCite one.
   */
  repository_id: string;
  url: string | null;
}
/**
 * Repositories a researcher may choose: those the pinned re3data export, and DataCite
 * snapshot, hold that `query` names, or, when `suggested`, those the deployment offers before a
 * search: its institution's repositories first.
 */
export interface RepositorySearch {
  query: string;
  repositories: RepositoryMatch[];
  /**
   * The re3data export searched.
   */
  snapshot_ref: string;
  suggested: boolean;
}
/**
 * A single-use ticket for the deposit broker, and where the browser takes it to connect,
 * read or disconnect the person's own repository account (`POST /api/repository-account/ticket`).
 */
export interface RepositoryTicket {
  deposit_broker_url: string;
  expires_at: string;
  ticket: string;
}
/**
 * A run that has ended, as `POST /api/runs` or a conversation's turn answers it.
 */
export interface RunResult {
  checks: Checks;
  envelope: Envelope;
}
/**
 * What a list of runs shows of one (`GET /api/runs`, `dd_harness.listing.run_summary`).
 */
export interface RunRow {
  /**
   * The name of the person the run acted for; null for a run stored before runs named one.
   */
  acting_for: string | null;
  agent_id: string;
  completed_at: string;
  invocation_id: string;
  status: OutcomeStatus;
}
/**
 * The folders on its own machine the deployment names, which a local install may describe.
 */
export interface ServerFolderRoots {
  roots: string[];
}
/**
 * A conversation the server started, and the project it was started in
 * (`POST /api/conversations`).
 */
export interface Started {
  conversation_id: string;
  /**
   * Null where the server keeps no projects.
   */
  project_id: string | null;
}
/**
 * The escalations routed to the signed-in steward's teams, the oldest first.
 */
export interface StewardQueue {
  escalations: QueuedEscalation[];
}
/**
 * A stored run with its request (`GET /api/runs/{id}`).
 */
export interface StoredRun {
  checks: Checks;
  envelope: Envelope;
  request: InvocationRequest | null;
}
/**
 * A single-use enrolment ticket, and where the browser takes it with the person's key
 * (`POST /api/model-account/ticket`).
 */
export interface Ticket {
  broker_url: string;
  expires_at: string;
  ticket: string;
}
