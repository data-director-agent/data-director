/**
 * A type-level check of what the generated API types (`api/generated/responses.ts`) leave to
 * hand-written ones (docs/specs/app.md, "API types"). `check_fixture` (`app/tests/support.py`)
 * rewrites each golden fixture in `fixtures/` from the server's real response and checks it
 * against the route's response model, from which the generated types are made, so a fixture of a
 * response typed wholly by the models needs no check here. These remain, and `npm run typecheck`
 * fails when one no longer fits:
 *
 * - responses the app's models do not describe: a contract class the app sends as it is
 *   (`RepositoryRequirements`, `ResearcherRecord`) and the model broker's account;
 * - responses that carry a contract shape the models name by `tsType` and the shell types by hand
 *   (`Envelope`, `Question`, `Principal`, `ProjectFact`, `DocumentQuestion`, the agent card's
 *   uses);
 * - the turn inputs of a conversation, which the model leaves open and the shell reads.
 *
 * JSON widens a string-literal union to `string`, so each type is compared as `Wide<T>`.
 * `satisfies` reports a missing or mistyped field; it does not report an extra one, and a renamed
 * optional field passes. Nothing here runs, and nothing imports the file.
 *
 * Every fixture `check_fixture` writes is here, refusals as well as answers. `inventory-left-out`
 * is not: it is written by hand, as what a test sends the server, not what the server says.
 */

import type {
  Escalation,
  Notices,
  ProjectEscalations,
  ProjectRuns,
  ProjectStewarding,
  RunResult,
  StewardQueue,
} from "./api/generated/responses";
import type { Conversation } from "./conversation/types";
import type { RawAgentsResponse } from "./manifest/types";
import type { RawModelAccount, RawRefusal } from "./model-account/api";
import type {
  DeletedProject,
  ProjectDocuments,
  ProjectIntake,
  ProjectSummary,
  RepositoryRequirements,
} from "./project/api";
import type { ResearcherRecord } from "./project/researcher";
import type { ProjectFacts } from "./project/facts";
import type { ProjectMembers } from "./project/members";
import type { Problem } from "./run/types";

import agents from "../fixtures/agents.json";
import agentsSeveral from "../fixtures/agents-several.json";
import conversation from "../fixtures/conversation.json";
import conversationAnswered from "../fixtures/conversation-answered.json";
import conversationQuestion from "../fixtures/conversation-question.json";
import conversationTurn from "../fixtures/conversation-turn.json";
import escalationResolved from "../fixtures/escalation-resolved.json";
import escalations from "../fixtures/escalations.json";
import intakeComplete from "../fixtures/intake-complete.json";
import intakePending from "../fixtures/intake-pending.json";
import modelAccount from "../fixtures/model-account.json";
import modelAccountRejected from "../fixtures/model-account-rejected.json";
import modelAccountNone from "../fixtures/model-account-none.json";
import notices from "../fixtures/notices.json";
import orcidRecord from "../fixtures/orcid-record.json";
import projectMembers from "../fixtures/project-members.json";
import projectMembersLastOwner from "../fixtures/project-members-last-owner.json";
import projectAnswers from "../fixtures/project-answers.json";
import projectCreated from "../fixtures/project-created.json";
import projectDocuments from "../fixtures/project-documents.json";
import projectRevised from "../fixtures/project-revised.json";
import projectFacts from "../fixtures/project-facts.json";
import projectFactsDecided from "../fixtures/project-facts-decided.json";
import projectFactsForbidden from "../fixtures/project-facts-forbidden.json";
import stewardQueue from "../fixtures/steward-queue.json";
import stewarding from "../fixtures/stewarding.json";
import projectFairnessRuns from "../fixtures/project-fairness-runs.json";
import projectResearchers from "../fixtures/project-researchers.json";
import projects from "../fixtures/projects.json";
import projectsDeleted from "../fixtures/projects-deleted.json";
import repositoryChosen from "../fixtures/repository-chosen.json";
import runAbstained from "../fixtures/run-abstained.json";
import runSucceeded from "../fixtures/run-succeeded.json";

/**
 * `T` as JSON can state it: every string, including a literal union, is a `string`. An object may
 * carry fields `T` does not name, which also keeps TypeScript from refusing a fixture for sharing
 * no field with a type whose fields are all optional (the envelope's `telemetry`).
 */
type Wide<T> = T extends string
  ? string
  : T extends readonly (infer Item)[]
    ? Wide<Item>[]
    : T extends object
      ? { [Key in keyof T]: Wide<T[Key]> } & Record<string, unknown>
      : T;

// Agents (their cards' model, skill, tool and schema uses), and the broker's model account.
void (agents satisfies Wide<RawAgentsResponse>);
void (agentsSeveral satisfies Wide<RawAgentsResponse>);
void (modelAccount satisfies Wide<RawModelAccount>);
void (modelAccountNone satisfies Wide<RawModelAccount>);
void (modelAccountRejected satisfies Wide<RawRefusal>);

// Conversations and runs (envelopes; the turns' inputs).
void (conversation satisfies Wide<Conversation>);
void (conversationTurn satisfies Wide<RunResult>);
void (conversationAnswered satisfies Wide<Conversation>);
void (conversationQuestion satisfies Wide<Conversation>);
void (runSucceeded satisfies Wide<RunResult>);
void (runAbstained satisfies Wide<RunResult>);

// Projects (principals, document questions, facts, intake questions), and the contract classes
// the app sends as they are.
void (projects satisfies Wide<ProjectSummary>[]);
void (projectCreated satisfies Wide<ProjectSummary>);
void (projectsDeleted satisfies Wide<DeletedProject>[]);
void (projectDocuments satisfies Wide<ProjectDocuments>);
void (projectAnswers satisfies Wide<ProjectDocuments>);
void (projectRevised satisfies Wide<ProjectDocuments>);
void (projectFacts satisfies Wide<ProjectFacts>);
void (projectFactsDecided satisfies Wide<ProjectFacts>);
void (projectFactsForbidden satisfies Wide<Problem>);
void (projectFairnessRuns satisfies Wide<ProjectRuns>);
void (projectMembers satisfies Wide<ProjectMembers>);
void (projectMembersLastOwner satisfies Wide<Problem>);
void (escalations satisfies Wide<ProjectEscalations>);
void (escalationResolved satisfies Wide<Escalation>);
void (stewardQueue satisfies Wide<StewardQueue>);
void (notices satisfies Wide<Notices>);
void (stewarding satisfies Wide<ProjectStewarding>);
void (projectResearchers satisfies Wide<ResearcherRecord>[]);
void (orcidRecord satisfies Wide<ResearcherRecord>);
void (intakePending satisfies Wide<ProjectIntake>);
void (intakeComplete satisfies Wide<ProjectIntake>);
void (repositoryChosen satisfies Wide<RepositoryRequirements>);
