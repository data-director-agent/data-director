// The golden fixtures (../fixtures) are rewritten from real server responses by the Python tests
// (app/tests/support.py, check_fixture). This file checks each one against the interface the
// shell reads it as, so that a field renamed on the server fails `npm run typecheck` instead of
// breaking the shell at run time (#981). The test below fails when a fixture is added without
// being listed here.
// @vitest-environment node
import { readdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import agentsSeveral from "../fixtures/agents-several.json";
import agents from "../fixtures/agents.json";
import conversationAnswered from "../fixtures/conversation-answered.json";
import conversationQuestion from "../fixtures/conversation-question.json";
import conversationTurn from "../fixtures/conversation-turn.json";
import conversation from "../fixtures/conversation.json";
import intakeComplete from "../fixtures/intake-complete.json";
import intakePending from "../fixtures/intake-pending.json";
import modelAccountNone from "../fixtures/model-account-none.json";
import modelAccountTicket from "../fixtures/model-account-ticket.json";
import modelAccount from "../fixtures/model-account.json";
import orcidRecord from "../fixtures/orcid-record.json";
import policy from "../fixtures/policy.json";
import processFlow from "../fixtures/process-flow.json";
import projectAnswers from "../fixtures/project-answers.json";
import projectCreated from "../fixtures/project-created.json";
import projectDisclosure from "../fixtures/project-disclosure.json";
import projectDocuments from "../fixtures/project-documents.json";
import projectPackage from "../fixtures/project-package.json";
import projectResearchers from "../fixtures/project-researchers.json";
import projectsDeleted from "../fixtures/projects-deleted.json";
import projects from "../fixtures/projects.json";
import repositoriesSuggested from "../fixtures/repositories-suggested.json";
import repositoryChosen from "../fixtures/repository-chosen.json";
import runAbstained from "../fixtures/run-abstained.json";
import runSucceeded from "../fixtures/run-succeeded.json";
import sessionDevelopment from "../fixtures/session-development.json";
import sessionSignedIn from "../fixtures/session-signed-in.json";
import sessionSignedOut from "../fixtures/session-signed-out.json";
import type { Conversation } from "./conversation/types";
import type { ProcessFlow } from "./flow/types";
import type { RawAgentsResponse } from "./manifest/types";
import type { RawModelAccount, Ticket } from "./model-account/api";
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
} from "./project/api";
import type { RunResult } from "./run/types";
import type { RawSession } from "./session/api";

/**
 * `T` with its literal types widened (`"user" | "agent"` to `string`), because TypeScript types
 * an imported JSON file's strings as `string`. Field names, nesting, nullability and the kind of
 * each value are still checked, which is what a renamed or restructured field breaks.
 *
 * An object whose fields are all optional, such as an envelope's `telemetry`, also accepts fields
 * the shell does not read: otherwise TypeScript rejects a value that has none of the optional
 * ones, as a run that called no model has none. A renamed optional field is therefore not caught
 * here; generating these types from the server's models (#981) will catch it.
 */
type Loose<T> = T extends string
  ? string
  : T extends number
    ? number
    : T extends boolean
      ? boolean
      : T extends readonly (infer U)[]
        ? Loose<U>[]
        : T extends object
          ? object extends T
            ? { [K in keyof T]: Loose<T[K]> } & Record<string, unknown>
            : { [K in keyof T]: Loose<T[K]> }
          : T;

// Each entry is a fixture checked against its interface. `satisfies` reports a missing field or
// one of the wrong kind.
const typed = {
  "agents-several.json": agentsSeveral satisfies Loose<RawAgentsResponse>,
  "agents.json": agents satisfies Loose<RawAgentsResponse>,
  "conversation-answered.json": conversationAnswered satisfies Loose<Conversation>,
  "conversation-question.json": conversationQuestion satisfies Loose<Conversation>,
  "conversation-turn.json": conversationTurn satisfies Loose<RunResult>,
  "conversation.json": conversation satisfies Loose<Conversation>,
  "intake-complete.json": intakeComplete satisfies Loose<ProjectIntake>,
  "intake-pending.json": intakePending satisfies Loose<ProjectIntake>,
  "model-account-none.json": modelAccountNone satisfies Loose<RawModelAccount>,
  "model-account-ticket.json": modelAccountTicket satisfies Loose<Ticket>,
  "model-account.json": modelAccount satisfies Loose<RawModelAccount>,
  "orcid-record.json": orcidRecord satisfies Loose<ResearcherRecord>,
  "policy.json": policy satisfies Loose<Policy>,
  "process-flow.json": processFlow satisfies Loose<ProcessFlow>,
  "project-answers.json": projectAnswers satisfies Loose<ProjectDocuments>,
  "project-created.json": projectCreated satisfies Loose<ProjectSummary>,
  "project-disclosure.json": projectDisclosure satisfies Loose<Disclosure>,
  "project-documents.json": projectDocuments satisfies Loose<ProjectDocuments>,
  "project-package.json": projectPackage satisfies Loose<BuiltPackage>,
  "project-researchers.json": projectResearchers satisfies Loose<ResearcherRecord[]>,
  "projects-deleted.json": projectsDeleted satisfies Loose<DeletedProject[]>,
  "projects.json": projects satisfies Loose<ProjectSummary[]>,
  "repositories-suggested.json": repositoriesSuggested satisfies Loose<RepositorySearch>,
  "repository-chosen.json": repositoryChosen satisfies Loose<RepositoryRequirements>,
  "run-abstained.json": runAbstained satisfies Loose<RunResult>,
  "run-succeeded.json": runSucceeded satisfies Loose<RunResult>,
  "session-development.json": sessionDevelopment satisfies Loose<RawSession>,
  "session-signed-in.json": sessionSignedIn satisfies Loose<RawSession>,
  "session-signed-out.json": sessionSignedOut satisfies Loose<RawSession>,
};

// The check itself: a response whose required field was renamed on the server no longer
// satisfies its interface, so this line fails to compile without the directive.
const { project_id: renamed, ...withoutId } = projectCreated;
// @ts-expect-error `project_id` is missing, as it would be if the server renamed it.
void ({ ...withoutId, id: renamed } satisfies Loose<ProjectSummary>);

// Fixtures that are not a server response the shell reads as one interface.
const untyped = new Set([
  // A refusal: a problem document with a validation report, read through `Problem`.
  "project-package-refused.json",
  // The broker's refusal of a key, `{ reason }`, read by `reasonText`.
  "model-account-rejected.json",
  // Written by hand for one test: an inventory, what is sent and what is left out.
  "inventory-left-out.json",
]);

describe("fixtures", () => {
  it("checks every fixture against an interface or says why not", () => {
    const fixtures = readdirSync(fileURLToPath(new URL("../fixtures", import.meta.url))).filter(
      (name) => name.endsWith(".json"),
    );
    const unlisted = fixtures.filter((name) => !(name in typed) && !untyped.has(name));
    expect(unlisted).toEqual([]);
  });
});
