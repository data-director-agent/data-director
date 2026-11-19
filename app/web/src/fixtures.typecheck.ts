/**
 * A type-level check that each golden fixture in `fixtures/` fits the interface the shell reads
 * it with (docs/specs/app.md, "API types"). `npm run typecheck` fails when a fixture, which
 * `app/tests/support.py` `check_fixture` rewrites from the server's real response, no longer
 * fits: a field the server renamed or dropped, or whose type changed.
 *
 * JSON widens a string-literal union to `string`, so each interface is compared as `Wide<T>`.
 * `satisfies` reports a missing or mistyped field; it does not report an extra one, and a renamed
 * optional field passes. Nothing here runs, and nothing imports the file.
 *
 * Every fixture `check_fixture` writes is here, refusals as well as answers. `inventory-left-out`
 * is not: it is written by hand, as what a test sends the server, not what the server says.
 */

import type { Conversation, HistoryEntry } from "./conversation/types";
import type { ProcessFlow } from "./flow/types";
import type { RawAgentsResponse } from "./manifest/types";
import type { RawModelAccount, RawRefusal, Ticket } from "./model-account/api";
import type { Policy } from "./policy/api";
import type {
  BuiltPackage,
  DeletedProject,
  Disclosure,
  ProjectDocuments,
  ProjectIntake,
  ProjectSummary,
  RepositoryRequirements,
  RepositorySearch,
  ResearcherRecord,
  Validation,
} from "./project/api";
import type { ProjectFacts } from "./project/facts";
import type { Problem, RunResult } from "./run/types";
import type { RawSession } from "./session/api";

import agents from "../fixtures/agents.json";
import agentsSeveral from "../fixtures/agents-several.json";
import conversation from "../fixtures/conversation.json";
import conversationAnswered from "../fixtures/conversation-answered.json";
import conversationQuestion from "../fixtures/conversation-question.json";
import conversationTurn from "../fixtures/conversation-turn.json";
import intakeComplete from "../fixtures/intake-complete.json";
import intakePending from "../fixtures/intake-pending.json";
import modelAccount from "../fixtures/model-account.json";
import modelAccountRejected from "../fixtures/model-account-rejected.json";
import modelAccountNone from "../fixtures/model-account-none.json";
import modelAccountTicket from "../fixtures/model-account-ticket.json";
import orcidRecord from "../fixtures/orcid-record.json";
import policy from "../fixtures/policy.json";
import processFlow from "../fixtures/process-flow.json";
import projectAnswers from "../fixtures/project-answers.json";
import projectCreated from "../fixtures/project-created.json";
import projectDisclosure from "../fixtures/project-disclosure.json";
import projectDocuments from "../fixtures/project-documents.json";
import projectFacts from "../fixtures/project-facts.json";
import projectFactsDecided from "../fixtures/project-facts-decided.json";
import projectFactsForbidden from "../fixtures/project-facts-forbidden.json";
import projectPackage from "../fixtures/project-package.json";
import projectPackageRefused from "../fixtures/project-package-refused.json";
import projectResearchers from "../fixtures/project-researchers.json";
import projects from "../fixtures/projects.json";
import projectsDeleted from "../fixtures/projects-deleted.json";
import repositoriesSuggested from "../fixtures/repositories-suggested.json";
import repositoryChosen from "../fixtures/repository-chosen.json";
import runAbstained from "../fixtures/run-abstained.json";
import runSucceeded from "../fixtures/run-succeeded.json";
import sessionDevelopment from "../fixtures/session-development.json";
import sessionSignedIn from "../fixtures/session-signed-in.json";
import sessionSignedOut from "../fixtures/session-signed-out.json";

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

// Sessions, policy, agents, model account.
void (sessionSignedIn satisfies Wide<RawSession>);
void (sessionSignedOut satisfies Wide<RawSession>);
void (sessionDevelopment satisfies Wide<RawSession>);
void (policy satisfies Wide<Policy>);
void (agents satisfies Wide<RawAgentsResponse>);
void (agentsSeveral satisfies Wide<RawAgentsResponse>);
void (modelAccount satisfies Wide<RawModelAccount>);
void (modelAccountNone satisfies Wide<RawModelAccount>);
void (modelAccountTicket satisfies Wide<Ticket>);
void (modelAccountRejected satisfies Wide<RawRefusal>);

// The process flow and conversations.
void (processFlow satisfies Wide<ProcessFlow>);
void (conversation satisfies Wide<Conversation>);
void (conversationTurn satisfies Wide<RunResult>);
void (conversationAnswered.history satisfies Wide<HistoryEntry>[]);
void (conversationQuestion.history satisfies Wide<HistoryEntry>[]);

// Runs.
void (runSucceeded satisfies Wide<RunResult>);
void (runAbstained satisfies Wide<RunResult>);

// Projects.
void (projects satisfies Wide<ProjectSummary>[]);
void (projectCreated satisfies Wide<ProjectSummary>);
void (projectsDeleted satisfies Wide<DeletedProject>[]);
void (projectDocuments satisfies Wide<ProjectDocuments>);
void (projectAnswers satisfies Wide<ProjectDocuments>);
void (projectDisclosure satisfies Wide<Disclosure>);
void (projectPackage satisfies Wide<BuiltPackage>);
void (projectPackageRefused satisfies Wide<Problem & { validation: Validation }>);
void (projectFacts satisfies Wide<ProjectFacts>);
void (projectFactsDecided satisfies Wide<ProjectFacts>);
void (projectFactsForbidden satisfies Wide<Problem>);
void (projectResearchers satisfies Wide<ResearcherRecord>[]);
void (orcidRecord satisfies Wide<ResearcherRecord>);
void (intakePending satisfies Wide<ProjectIntake>);
void (intakeComplete satisfies Wide<ProjectIntake>);
void (repositoriesSuggested satisfies Wide<RepositorySearch>);
void (repositoryChosen satisfies Wide<RepositoryRequirements>);
