/**
 * The home page: a conversation with the orchestrator (docs/specs/app.md), in the centre of the
 * workspace (§18), in the project the shell is working in. The project's conversations are on the
 * left, an overview of it on the right, and the Blueprint's phases in a strip above. New
 * conversation starts another thread in the same project; with no project active, the first
 * message starts one, which becomes the active project. The open conversation is named in the
 * address (`?conversation=`), so a reload or a link reopens it and a message sent after it
 * continues it. Switching project closes the open conversation. A delegated run opens inside its card in the
 * transcript (§14).
 *
 * The orchestrator is the agent the profile names (docs/specs/app.md), never one the shell picks.
 * When the profile names none, the named agent is not running, its card does not declare
 * `delegation` grounding, or the policy does not permit it, the page says which and links to the
 * directory (§12). The server builds each turn's history; the page sends the agent, the message
 * and the turn it follows, the latest one the page shows (docs/specs/orchestration.md).
 * Until there is authentication (#17) the conversation acts for the operator (docs/specs/policy-and-identity.md).
 *
 * While a reply is awaited the message sits in the transcript beside a pulsing sign that the
 * orchestrator is working. A new reply is announced in a polite live region, with any document
 * version the turn drafted once the project's documents have been read again, the busy state is
 * announced, and focus returns to the message box. The project's documents are read once for
 * both the transcript's cards and the side bar's list.
 *
 * A reply may ask a choice question, which the transcript shows as choices; sending the answer
 * takes the same path as a typed message, with the answer beside the labels chosen. The message
 * box stays usable, so the researcher may ignore the question and type instead.
 *
 * A message may attach a `dd-inventory` file, chosen with the Attach button, dropped on the form
 * or pasted, which shows as a chip and goes to the conversation's project, never into the text
 * (#443, docs/specs/app.md). A file read as an inventory is first opened to be checked, and is
 * attached, without whatever the researcher left out, only when they confirm (#472). Making one is offered in the project's panel, not under the
 * message box (AddInventory.tsx, #553).
 *
 * The same Attach a file button, or a drop, takes a supporting document as plain text or
 * Markdown, which is opened to be checked, attached as a chip only when the researcher confirms,
 * and goes to the project, never into the text (docs/specs/app.md). A message may carry one
 * inventory and one document.
 *
 * A step of the data journey, or one of the prompts an empty conversation offers, starts a new
 * conversation with the step's prompt in the message box, unsent. A message already being written
 * is replaced only when the researcher confirms.
 *
 * The page puts together hooks that each hold one part: the open conversation and its turns
 * (`useConversationTurns`), what a message carries (`useAttachments`), and the project's
 * documents, progress and intake (`useProjectDocuments`, `useProjectProgress`, `useIntake`), each
 * read with `useResource`. Until the first of those reads have landed, and the flow and the
 * earlier conversations with them, the page shows one line in their place, so that what arrives
 * late never moves a button the researcher is about to press.
 */

import { useMemo, useRef, useState } from "react";

import { documentReaders } from "../../conversation/documentation";
import type { ReplyAnswers } from "../../conversation/question";
import type { FlowStep } from "../../flow/types";
import type { Directory } from "../../manifest/normalise";
import { useActiveProject } from "../../project/active";
import { useProjectApi } from "../../project/api";
import { homePath, navigate, useLocation } from "../../route";
import type { Envelope } from "../../run/types";
import { ContextPanel } from "../workspace/ContextPanel";
import { FAIRNESS_CLASS } from "../../project/fairness";
import { PhaseTracker } from "../workspace/PhaseTracker";
import { useFlowLoad } from "../workspace/useFlowLoad";
import { useAskAbout, useAskAboutQuestion } from "./useAskAbout";
import { Workspace } from "../workspace/Workspace";
import { ProjectSwitcher } from "../project/ProjectSwitcher";
import { useAnnounce } from "../ui/Announcer";
import { PageLoading } from "../ui/PageLoading";
import { Composer } from "./Composer";
import { EarlierConversations } from "./EarlierConversations";
import {
  LinkedRun,
  askInBox,
  NoConversation,
  OpenIntake,
  chosenRepository,
  holdsRun,
  offeredPrompts,
  projectHandlers,
  projectNamed,
  restoreDays,
  trackedProgress,
  workspaceReady,
} from "./ConversationHomeParts";
import { whyUnusable } from "./orchestrator";
import { StartFromStep } from "./StartFromStep";
import { Transcript } from "./Transcript";
import { useAttachments } from "./useAttachments";
import { useConversationTurns } from "./useConversationTurns";
import { useIntake } from "./useIntake";
import { useProjectDocuments } from "./useProjectDocuments";
import { useProjectProgress } from "./useProjectProgress";

export function ConversationHome({ directory }: { directory: Directory }) {
  const projectApi = useProjectApi();
  const named = directory.orchestratorId;
  const orchestrator = directory.agents.find((a) => a.id === named);
  const unusable = whyUnusable(named, orchestrator);
  const { projectId, projects, reloadProjects } = useActiveProject();
  const [text, setText] = useState("");
  const announce = useAnnounce();
  // A step whose prompt waits on the researcher's leave to replace the message being written.
  const [replacing, setReplacing] = useState<FlowStep | null>(null);
  const params = new URLSearchParams(useLocation().split("?")[1]);
  const runId = params.get("run");
  // The open conversation is kept in the address, so a reload or a link reopens it.
  const urlConversation = params.get("conversation");
  const box = useRef<HTMLTextAreaElement>(null);

  const attachments = useAttachments(box, announce, directory.documentsAllowed);
  const readers = useMemo(
    () => documentReaders(directory.agents, directory.orchestratorId),
    [directory.agents, directory.orchestratorId],
  );
  const turns = useConversationTurns({
    orchestratorId: orchestrator?.id,
    runId,
    urlConversation,
    box,
    announce: announce,
    setText,
    restore: attachments.restore,
    clearAttachError: attachments.clearError,
  });
  const { conversation, busy, sent, turnCount, quiet } = turns;
  const { inventory: attached, document: attachedDocument } = attachments;
  const writing = Boolean(text.trim()) || attachments.carries;
  const { documents, answered } = useProjectDocuments(
    projectId,
    turnCount,
    turns.awaitedDrafts,
    announce,
  );
  const progress = useProjectProgress(projectId, turnCount);
  const intakeRead = useIntake(projectId, turnCount, {
    progressed: progress.set,
    announce: announce,
    failed: turns.setError,
  });
  const { intake } = intakeRead;

  const tracked = trackedProgress(projectId, progress, {
    projectApi,
    documents,
    // A new conversation is not started while a reply is awaited.
    startConversation: busy ? undefined : (step: FlowStep) => startStep(step),
    answerIntakeAgain: intakeRead.intake ? intakeRead.openAgain : undefined,
  });

  const flow = useFlowLoad();

  useAskAbout(flow, setText, box, {
    conversation: urlConversation,
    run: runId,
  });
  useAskAboutQuestion(documents, setText, box, {
    conversation: urlConversation,
    run: runId,
  });

  const frame = {
    project: <ProjectSwitcher />,
    phases: <PhaseTracker load={flow} tracked={tracked} />,
  };
  const project = projectNamed(projects, projectId);

  // Drawn whole once what it reads on load has landed (#1328).
  const ready = workspaceReady({
    flow,
    projectId,
    reads: [turns.pastSettled, progress.settled, intakeRead.settled, documents.state !== "loading"],
    quiet,
  });

  if (unusable || !orchestrator) {
    return (
      <PageLoading ready={ready} said="Opening the project…">
        <NoConversation
          frame={frame}
          why={unusable}
          projectId={projectId}
          project={project}
        />
      </PageLoading>
    );
  }

  async function send() {
    await turns.deliver(
      text.trim(),
      { inventory: attached, document: attachedDocument },
      null,
    );
  }

  /** Sends the answers to the latest turn's questions, said in words as `message`. What is in
   * the message box stays there. */
  async function answerQuestions(answers: ReplyAnswers, message: string) {
    await turns.deliver(message, { inventory: null, document: null }, answers);
  }

  // The finished intake hands over to the conversation: the researcher's press sends their
  // opening turn, naming the suggested step, by the ordinary path.
  function startFromIntake(message: string) {
    intakeRead.close();
    void turns.deliver(message, { inventory: null, document: null }, null);
  }

  /** Starts a new conversation about `step`, asking first if a message is being written. */
  function startStep(step: FlowStep) {
    if (writing) setReplacing(step);
    else beginWith(step);
  }

  /** A new conversation, with the step's prompt in the box to edit and send. */
  function beginWith(step: FlowStep) {
    setReplacing(null);
    turns.reset();
    setText(step.prompt);
    announce(
      `New conversation about ${step.label}. The message box holds a suggested message: edit it if you wish, then send.`,
    );
    requestAnimationFrame(() => {
      const input = box.current;
      if (!input) return;
      input.focus();
      input.setSelectionRange(input.value.length, input.value.length);
    });
  }

  // Opening a run shows it in its card and closing it hides it; focus stays on the card's button.
  function toggleRun(envelope: Envelope) {
    navigate(
      homePath({
        conversation: urlConversation,
        run: envelope.invocation_id === runId ? null : envelope.invocation_id,
      }),
    );
  }

  return (
    <PageLoading ready={ready} said="Opening the project…">
      <Workspace
        {...frame}
        title="Talk to Data Director"
        titleHidden
        centre={
          <section
            aria-labelledby="conversation-heading"
            className="conversation-main"
          >
            <h2 id="conversation-heading" className="visually-hidden">
              Conversation
            </h2>
            <OpenIntake
              projectId={projectId}
              read={intakeRead}
              flow={flow}
              onStart={quiet ? startFromIntake : undefined}
              onAnnounce={announce}
            />
            {(turnCount > 0 || sent !== null) && (
              <Transcript
                conversation={conversation}
                agents={directory.agents}
                onToggleRun={toggleRun}
                selectedRun={runId}
                documents={
                  documents.state === "loaded" ? documents.documents : null
                }
                pending={sent && { agentId: orchestrator.id, ...sent, live: turns.live }}
                onAnswer={(answers, message) =>
                  void answerQuestions(answers, message)
                }
                chosenRepository={chosenRepository(project)}
                project={project}
                onRetry={(message) =>
                  void turns.deliver(message, { inventory: null, document: null }, null)
                }
                onDocumentWrite={(message) =>
                  void turns.deliver(message, { inventory: null, document: null }, null)
                }
                {...projectHandlers(projectId, answered, reloadProjects)}
              />
            )}
            <StartFromStep
              offered={offeredPrompts(
                flow,
                tracked,
                quiet && !writing && !intake?.open,
              )}
              replacing={replacing}
              onChoose={beginWith}
              onCancel={() => setReplacing(null)}
            />
            {runId && !holdsRun(conversation, runId) && (
              <LinkedRun runId={runId} agents={directory.agents} />
            )}
            <Composer
              box={box}
              text={text}
              onText={setText}
              attachments={attachments}
              busy={busy}
              onSend={() => void send()}
              readers={readers}
            />
            {turns.error && (
              <div role="alert" className="callout status-danger">
                <p>{turns.error}</p>
              </div>
            )}
          </section>
        }
        history={
          <EarlierConversations
            conversations={turns.past.filter(
              (c) => (c.project_id ?? null) === projectId,
            )}
            currentId={turns.conversationId}
            onOpen={(id) => void turns.reopen(id)}
            onNew={turns.reset}
            onDeleted={(id) => {
              turns.deleted(id);
              void reloadProjects();
            }}
            restoreDays={restoreDays(project)}
          />
        }
        context={
          <ContextPanel
            projectId={projectId}
            project={project}
            conversation={conversation}
            documents={documents}
            flow={flow}
            progress={progress.progress}
            fairFeedback={directory.agents.some((a) => a.payload === FAIRNESS_CLASS)}
            refresh={turnCount}
            onAsk={(question) => askInBox(question, text, setText, box)}
            onInventorySaved={() => void reloadProjects()}
          />
        }
      />
    </PageLoading>
  );
}
