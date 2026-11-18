/**
 * The pieces of the conversation home page that need no state of their own: what the phase
 * tracker, the starting prompts and the transcript are given, and the cards the page shows beside
 * the transcript (see `ConversationHome`).
 */

import { type ComponentProps } from "react";

import { X } from "lucide-react";
import { startablePrompts } from "../../flow/prompts";
import type { FlowStep } from "../../flow/types";
import type { Directory } from "../../manifest/normalise";
import type {
  ProjectApi,
  ProjectDocuments,
  ProjectSummary,
} from "../../project/api";
import type { DocumentsRead } from "../../project/drafted";
import { Link, navigate } from "../../route";
import type { Conversation } from "../../conversation/types";
import { ContextPanel } from "../workspace/ContextPanel";
import type { FlowLoad, TrackedProgress } from "../workspace/PhaseTracker";
import { Workspace } from "../workspace/Workspace";
import { Button } from "../ui/Button";
import { IntakeCard } from "./IntakeCard";
import { RunDetail } from "./RunDetail";
import type { IntakeRead } from "./useIntake";
import type { ProjectProgressRead } from "./useProjectProgress";

/** The project's progress for the phase tracker, with how to change it, once it has been read. */
export function trackedProgress(
  projectId: string | null,
  read: ProjectProgressRead,
  how: {
    projectApi: ProjectApi;
    documents: DocumentsRead;
    startConversation: ((step: FlowStep) => void) | undefined;
    answerIntakeAgain: ((projectId: string) => void) | undefined;
  },
): TrackedProgress | null {
  const { progress, change, error } = read;
  if (!projectId || !progress) return null;
  const { projectApi, documents, startConversation, answerIntakeAgain } = how;
  return {
    progress,
    chooseEntry: (entry) =>
      change(projectApi.chooseEntry(projectId, entry), projectId),
    markStep: (stepId, mark) =>
      change(projectApi.markStep(projectId, stepId, mark), projectId),
    error,
    projectId,
    ...(documents.state === "loaded" ? { documents: documents.documents } : {}),
    ...(startConversation ? { startConversation } : {}),
    ...(answerIntakeAgain
      ? { answerIntakeAgain: () => answerIntakeAgain(projectId) }
      : {}),
  };
}

/** The prompts a conversation yet to begin offers, from the steps that can be started now. */
export function offeredPrompts(
  flow: FlowLoad,
  tracked: TrackedProgress | null,
  offering: boolean,
) {
  if (!offering || !tracked || flow.state !== "loaded") return null;
  return startablePrompts(flow.flow, tracked.progress);
}

/** The repository chosen for the project, if one has been. */
export function chosenRepository(project: ProjectSummary | null): string | null {
  return project?.repository?.re3data_id ?? null;
}

/** Whether `runId` is one of the runs in the conversation's transcript. */
export function holdsRun(conversation: Conversation | null, runId: string): boolean {
  return Boolean(
    conversation?.turns
      .flatMap((t) => t.children)
      .some((c) => c.invocation_id === runId),
  );
}

/** The project's intake card, while it is open. */
export function OpenIntake({
  projectId,
  read,
  flow,
  onStart,
  onAnnounce,
}: {
  projectId: string | null;
  read: IntakeRead;
  flow: FlowLoad;
  onStart: ((message: string) => void) | undefined;
  onAnnounce: (said: string) => void;
}) {
  const { intake } = read;
  if (!projectId || !intake?.open) return null;
  return (
    <IntakeCard
      key={`${projectId}-${intake.again ? "again" : "pending"}`}
      intake={intake.intake}
      again={intake.again}
      flow={flow.state === "loaded" ? flow.flow : null}
      onAnswer={(questionId, values) =>
        read.answer(projectId, questionId, values)
      }
      onDismiss={() => read.dismiss(projectId)}
      onClose={read.close}
      onStart={onStart}
      onAnnounce={onAnnounce}
    />
  );
}

/** A run named in the address but not in the transcript, so that the link still opens it. */
export function LinkedRun({
  runId,
  agents,
}: {
  runId: string;
  agents: Directory["agents"];
}) {
  return (
    <section aria-labelledby="linked-run" className="callout">
      <h3 id="linked-run">
        Run <code>{runId}</code>
      </h3>
      <RunDetail invocationId={runId} agents={agents} idPrefix="linked-run" />
      <p>
        <Button icon={X} onPress={() => navigate("/")}>
          Close the run
        </Button>
      </p>
    </section>
  );
}

export function projectNamed(
  projects: ProjectSummary[],
  projectId: string | null,
): ProjectSummary | null {
  return projects.find((p) => p.project_id === projectId) ?? null;
}

/** For how many days a conversation deleted in `project` may be restored, if known. */
export function restoreDays(project: ProjectSummary | null): number | undefined {
  return project?.restore_days;
}

/** What the transcript does with the project's documents and repository choice; nothing outside a
 * project. */
export function projectHandlers(
  projectId: string | null,
  answered: (projectId: string, value: ProjectDocuments) => void,
  reloadProjects: () => void | Promise<void>,
) {
  if (!projectId) return {};
  return {
    onDocumentAnswered: (value: ProjectDocuments) => answered(projectId, value),
    // The panel reads the choice from the projects list, so it is read again.
    onRepositoryChosen: () => void reloadProjects(),
  };
}

/** The page when no orchestrator can be talked to: why, and the way to the agents. */
export function NoConversation({
  frame,
  why,
  projectId,
  project,
}: {
  frame: Pick<ComponentProps<typeof Workspace>, "project" | "phases">;
  why: string | null;
  projectId: string | null;
  project: ProjectSummary | null;
}) {
  return (
    <Workspace
      {...frame}
      title="No conversation is available"
      centre={
        <>
          <p>{why} You can still use each agent on its own.</p>
          <p>
            <Link to="/agents">Open the agent directory</Link>
          </p>
        </>
      }
      context={<ContextPanel projectId={projectId} project={project} />}
    />
  );
}
