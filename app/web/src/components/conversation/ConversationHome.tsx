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
 * attached, without whatever the researcher left out, only when they confirm (#472). Make an inventory, beside the button, opens a dialog that says how
 * to make one and ends by choosing it (#553).
 *
 * The same Attach a file button, or a drop, takes a supporting document as plain text or
 * Markdown, which is opened to be checked, attached as a chip only when the researcher confirms,
 * and goes to the project, never into the text (docs/specs/app.md). A message may carry one
 * inventory and one document.
 */

import {
  type ClipboardEvent,
  type DragEvent,
  type FormEvent,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";

import { Paperclip, SendHorizontal, X } from "lucide-react";
import { FileTrigger } from "react-aria-components";
import { TurnConflict, Unreachable, useConversationApi } from "../../conversation/api";
import { type ChoiceAnswer, replyQuestion } from "../../conversation/question";
import {
  type AttachedDocument,
  DOCUMENT_EXTENSIONS,
  NotADocument,
  isDocumentName,
  readDocument,
} from "../../conversation/documentation";
import {
  type AttachedInventory,
  NotAnInventory,
  looksLikeInventory,
  readInventory,
} from "../../conversation/inventory";
import { useFlowApi } from "../../flow/api";
import type { ProjectProgress } from "../../flow/types";
import type { Conversation, ConversationSummary } from "../../conversation/types";
import type { AgentView, Directory } from "../../manifest/normalise";
import { useActiveProject } from "../../project/active";
import { type ProjectDocuments, useProjectApi } from "../../project/api";
import { type DocumentsRead, draftedBy } from "../../project/drafted";
import { Link, homePath, navigate, useLocation } from "../../route";
import { OUTCOME } from "../../manifest/wording";
import { RunRefused, errorMessage } from "../../run/api";
import type { Envelope } from "../../run/types";
import { documentName } from "../../project/name";
import { STATES } from "../project/DocumentFacts";
import { ContextPanel } from "../workspace/ContextPanel";
import { type FlowLoad, PhaseTracker, type TrackedProgress } from "../workspace/PhaseTracker";
import { Workspace } from "../workspace/Workspace";
import { ProjectSwitcher } from "../project/ProjectSwitcher";
import { Button } from "../ui/Button";
import { EarlierConversations } from "./EarlierConversations";
import { InventoryReviewDialog } from "../inventory/InventoryReviewDialog";
import { MakeInventoryDialog } from "../inventory/MakeInventoryDialog";
import { DocumentChip } from "./DocumentChip";
import { DocumentReviewDialog } from "./DocumentReviewDialog";
import { InventoryChip } from "./InventoryChip";
import { RunDetail } from "./RunDetail";
import { Transcript } from "./Transcript";

/** Why the named orchestrator cannot be conversed with, or null when it can. */
function whyUnusable(named: string | null, agent: AgentView | undefined): string | null {
  if (named === null) {
    return "The policy in force names no agent to converse with.";
  }
  if (!agent) {
    return `The policy in force names ${named} to converse with, but it is not available.`;
  }
  if (agent.groundingMode !== "delegation") {
    return `The policy in force names ${named} to converse with, but it does not delegate to other agents.`;
  }
  if (agent.gate.kind === "not-permitted" || agent.gate.kind === "mismatch") {
    return `The policy in force does not permit ${named} to run here.`;
  }
  return null;
}

export function ConversationHome({ directory }: { directory: Directory }) {
  const api = useConversationApi();
  const flowApi = useFlowApi();
  const named = directory.orchestratorId;
  const orchestrator = directory.agents.find((a) => a.id === named);
  const unusable = whyUnusable(named, orchestrator);
  const { projectId, projects, setProjectId, reloadProjects } = useActiveProject();
  const [conversationId, setConversationId] = useState<string | null>(null);
  // The project of the open conversation, once it has been started or reopened.
  const [openProject, setOpenProject] = useState<string | null | undefined>(undefined);
  const [conversation, setConversation] = useState<Conversation | null>(null);
  const [past, setPast] = useState<ConversationSummary[]>([]);
  const [text, setText] = useState("");
  const [attached, setAttached] = useState<AttachedInventory | null>(null);
  // An inventory read from a file and being checked, not yet attached (#472).
  const [pending, setPending] = useState<AttachedInventory | null>(null);
  const [attachedDocument, setAttachedDocument] = useState<AttachedDocument | null>(null);
  // A document read from a file and being checked, not yet attached.
  const [pendingDocument, setPendingDocument] = useState<AttachedDocument | null>(null);
  const [attachError, setAttachError] = useState<string | null>(null);
  const [dropping, setDropping] = useState(false);
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState<{
    message: string;
    inventory: AttachedInventory | null;
    document: AttachedDocument | null;
  } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [announcement, setAnnouncement] = useState("");
  const [flow, setFlow] = useState<FlowLoad>({ state: "loading" });
  const params = new URLSearchParams(useLocation().split("?")[1]);
  const runId = params.get("run");
  // The open conversation is kept in the address, so a reload or a link reopens it.
  const urlConversation = params.get("conversation");
  // The conversation the page already holds, or has deliberately closed, so that the address
  // changing to it is not read as a request to load it.
  const handled = useRef<string | null>(null);
  const box = useRef<HTMLTextAreaElement>(null);

  const reloadPast = useCallback(
    (signal?: AbortSignal) => api.list(signal).then(setPast, () => undefined),
    [api],
  );

  useEffect(() => {
    const abort = new AbortController();
    void reloadPast(abort.signal);
    return () => abort.abort();
  }, [reloadPast]);

  // The project's documents, read when the conversation's project is known and again after each
  // turn, for the cards on the turns that drafted them and the side bar's list. A read is kept
  // with the project it is of, so that another project's documents are never shown.
  const projectApi = useProjectApi();
  const turnCount = conversation?.turns.length ?? 0;
  const [documentsOf, setDocumentsOf] = useState<{ projectId: string; read: DocumentsRead } | null>(
    null,
  );
  // The newest reply's announcement and the runs it made, until the documents are read and what
  // they drafted can be said too.
  const announceDrafts = useRef<{ said: string; invocationIds: string[] } | null>(null);
  useEffect(() => {
    if (!projectId) return;
    const abort = new AbortController();
    projectApi.documents(projectId, abort.signal).then(
      (value) => {
        setDocumentsOf({ projectId, read: { state: "loaded", documents: value.documents } });
        const pending = announceDrafts.current;
        announceDrafts.current = null;
        const drafted = pending ? draftedBy(pending.invocationIds, value.documents) : [];
        if (pending && drafted.length > 0) {
          const what = drafted.map(
            ({ document, version }) =>
              `${documentName(document)} drafted, version ${version.version}: ${STATES[version.state].label}.`,
          );
          setAnnouncement([pending.said, ...what].join(" "));
        }
      },
      (e: unknown) => {
        if (abort.signal.aborted) return;
        announceDrafts.current = null;
        setDocumentsOf({ projectId, read: { state: "failed", message: errorMessage(e) } });
      },
    );
    return () => abort.abort();
  }, [projectApi, projectId, turnCount]);
  const documents: DocumentsRead =
    projectId && documentsOf?.projectId === projectId ? documentsOf.read : { state: "loading" };

  // Where the project is in the flow, read with its documents: when the project is known and
  // after each turn. A read is kept with the project it is of, as the documents are.
  const [progressOf, setProgressOf] = useState<{ projectId: string; progress: ProjectProgress } | null>(
    null,
  );
  const [progressError, setProgressError] = useState<string | null>(null);
  useEffect(() => {
    if (!projectId) return;
    const abort = new AbortController();
    projectApi.progress(projectId, abort.signal).then(
      (progress) => setProgressOf({ projectId, progress }),
      () => undefined,
    );
    return () => abort.abort();
  }, [projectApi, projectId, turnCount]);
  const changeProgress = useCallback(
    (change: Promise<ProjectProgress>, of: string) => {
      change.then(
        (progress) => {
          setProgressError(null);
          setProgressOf({ projectId: of, progress });
        },
        (e: unknown) => setProgressError(errorMessage(e)),
      );
    },
    [],
  );
  const tracked: TrackedProgress | null =
    projectId && progressOf?.projectId === projectId
      ? {
          progress: progressOf.progress,
          chooseEntry: (entry) => changeProgress(projectApi.chooseEntry(projectId, entry), projectId),
          markStep: (stepId, mark) =>
            changeProgress(projectApi.markStep(projectId, stepId, mark), projectId),
          error: progressError,
        }
      : null;

  // The phases do not depend on the conversation: if they fail, only the tracker says so.
  useEffect(() => {
    const abort = new AbortController();
    flowApi.get(abort.signal).then(
      (loaded) => setFlow({ state: "loaded", flow: loaded }),
      (e: unknown) => abort.signal.aborted || setFlow({ state: "failed", message: errorMessage(e) }),
    );
    return () => abort.abort();
  }, [flowApi]);

  // A conversation closed by switching project is taken out of the address, and not read again
  // from it. This runs before the effect below, which would otherwise reopen it.
  const [closed, setClosed] = useState<{ id: string } | null>(null);
  useEffect(() => {
    if (closed === null) return;
    handled.current = closed.id;
    navigate(homePath({ run: runId }), true);
    // Only a closing is acted on; the run is read as it is then.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [closed]);

  // A conversation named in the address and not yet held, as after a reload or Back, is read and
  // opened in its own project.
  useEffect(() => {
    if (!urlConversation) {
      handled.current = null;
      return;
    }
    if (urlConversation === handled.current) return;
    const id = urlConversation;
    const abort = new AbortController();
    handled.current = id;
    api.get(id, abort.signal).then(
      (found) => {
        setConversation(found);
        setConversationId(id);
        setOpenProject(found.project_id ?? null);
        if ((found.project_id ?? null) !== projectId) setProjectId(found.project_id ?? null);
        setError(null);
      },
      (e: unknown) => {
        if (abort.signal.aborted) return;
        handled.current = null;
        setError(`Data Director could not open that conversation: ${errorMessage(e)}`);
        navigate(homePath({ run: runId }), true);
      },
    );
    return () => abort.abort();
    // Only the address decides what is loaded; the project is read as it is when the read lands.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [api, urlConversation]);

  // Switching project closes the conversation open in another; starting a project by sending the
  // first message does not, since the open conversation is the one that started it.
  if (openProject !== undefined && openProject !== projectId) {
    if (urlConversation) setClosed({ id: urlConversation });
    setConversationId(null);
    setConversation(null);
    setOpenProject(undefined);
    setError(null);
    setAnnouncement("");
  }

  const frame = {
    project: <ProjectSwitcher />,
    phases: <PhaseTracker load={flow} tracked={tracked} />,
  };
  const project = projects.find((p) => p.project_id === projectId) ?? null;

  if (unusable || !orchestrator) {
    return (
      <Workspace
        {...frame}
        title="No conversation is available"
        centre={
          <>
            <p>{unusable} You can still use each agent on its own.</p>
            <p>
              <Link to="/agents">Open the agent directory</Link>
            </p>
          </>
        }
        context={<ContextPanel projectId={projectId} project={project} />}
      />
    );
  }

  /**
   * Reads `text` as an inventory and opens it to be checked before it is attached, or says why
   * it cannot (#472).
   */
  function attach(content: string, name: string | null): boolean {
    try {
      setPending(readInventory(content, name));
      setAttachError(null);
      return true;
    } catch (e) {
      setAttachError(e instanceof NotAnInventory ? e.message : errorMessage(e));
      return false;
    }
  }

  /** Reads a text or Markdown file as a document and opens it to be checked, or says why not. */
  function attachDocument(content: string, name: string) {
    try {
      setPendingDocument(readDocument(content, name));
      setAttachError(null);
    } catch (e) {
      setAttachError(e instanceof NotADocument ? e.message : errorMessage(e));
    }
  }

  /** A file chosen or dropped: a document by its name, otherwise read as an inventory. */
  async function attachFile(file: File | undefined) {
    if (!file) return;
    try {
      const content = await file.text();
      if (isDocumentName(file.name)) attachDocument(content, file.name);
      else attach(content, file.name);
    } catch (e) {
      setAttachError(`Data Director could not read ${file.name}: ${errorMessage(e)}`);
    }
  }

  /**
   * A file chosen at the end of the Make an inventory dialog. Once it is attached the dialog's
   * button gives way to the chip, so focus goes to the message box rather than nowhere; if it is
   * not an inventory, the dialog's button stays and takes the focus back.
   */
  async function attachFromDialog(file: File) {
    await attachFile(file);
    requestAnimationFrame(() => {
      if (!document.activeElement || document.activeElement === document.body) box.current?.focus();
    });
  }

  /** The checked inventory, without what the researcher left out, becomes the chip. */
  function confirmInventory(checked: AttachedInventory) {
    setPending(null);
    setAttached(checked);
    setAnnouncement("Inventory attached.");
    requestAnimationFrame(() => box.current?.focus());
  }

  function discardInventory() {
    setPending(null);
    setAnnouncement("Inventory not attached.");
    requestAnimationFrame(() => box.current?.focus());
  }

  function confirmDocument(checked: AttachedDocument) {
    setPendingDocument(null);
    setAttachedDocument(checked);
    setAnnouncement(`${checked.name} attached.`);
    requestAnimationFrame(() => box.current?.focus());
  }

  function discardDocument() {
    setPendingDocument(null);
    setAnnouncement("Document not attached.");
    requestAnimationFrame(() => box.current?.focus());
  }

  function removeDocument() {
    const name = attachedDocument?.name ?? "Document";
    setAttachedDocument(null);
    setAnnouncement(`${name} removed.`);
    box.current?.focus();
  }

  function removeInventory() {
    setAttached(null);
    setAnnouncement("Inventory removed.");
    box.current?.focus();
  }

  // A whole inventory pasted into the box becomes a chip, not text (#443).
  function onPaste(event: ClipboardEvent<HTMLTextAreaElement>) {
    const pasted = event.clipboardData.getData("text");
    if (!looksLikeInventory(pasted)) return;
    event.preventDefault();
    attach(pasted, null);
  }

  function onDragOver(event: DragEvent<HTMLFormElement>) {
    if (!event.dataTransfer.types.includes("Files")) return;
    event.preventDefault();
    setDropping(true);
  }

  function onDrop(event: DragEvent<HTMLFormElement>) {
    if (!event.dataTransfer.types.includes("Files")) return;
    event.preventDefault();
    setDropping(false);
    void attachFile(event.dataTransfer.files[0]);
  }

  async function send(event: FormEvent) {
    event.preventDefault();
    await deliver(text.trim(), attached, null, attachedDocument);
  }

  /** Sends the answer to the latest turn's choice question, said in words as `message`. What is
   * in the message box stays there. */
  async function answerQuestion(answer: ChoiceAnswer, message: string) {
    await deliver(message, null, answer);
  }

  async function deliver(
    message: string,
    inventory: AttachedInventory | null,
    answer: ChoiceAnswer | null,
    attachedDoc: AttachedDocument | null = null,
  ) {
    if (!orchestrator || (!message && !inventory && !attachedDoc) || busy) return;
    // A typed message comes from the box, and goes back to it if the send fails.
    const fromBox = answer === null;
    setBusy(true);
    setError(null);
    setAttachError(null);
    setAnnouncement("Waiting for a reply.");
    // The message and its inventory move into the transcript while the reply is awaited, and
    // come back to the box if the send fails, so nothing typed or attached is lost.
    setSent({ message, inventory, document: attachedDoc });
    if (fromBox) {
      setText("");
      setAttached(null);
      setAttachedDocument(null);
    }
    let id = conversationId;
    let stored = false;
    // The latest turn this page shows: the server refuses the turn if the conversation has
    // moved on since, so a message sent again after a dropped connection never runs twice.
    const follows = conversation?.turns[conversation.turns.length - 1]?.invocation_id ?? null;
    try {
      if (id === null) {
        const started = await api.create(projectId);
        id = started.conversation_id;
        setOpenProject(started.project_id);
        // With no project active, the server started one: the shell is now working in it.
        if (started.project_id !== projectId) setProjectId(started.project_id);
        handled.current = id;
        navigate(homePath({ conversation: id, run: runId }), true);
      }
      setConversationId(id);
      const document = inventory?.document ?? null;
      await (answer
        ? api.sendTurn(id, orchestrator.id, message, follows, document, undefined, answer)
        : attachedDoc
          ? api.sendTurn(id, orchestrator.id, message, follows, document, undefined, null, attachedDoc)
          : api.sendTurn(id, orchestrator.id, message, follows, document));
      // The turn is stored: from here a failure is in showing the reply, not in sending it, so
      // the message must not come back to the box to be sent twice (#337).
      stored = true;
      // Once more if the first read gets no response: the reply is there to be read.
      const sentTo = id;
      const updated = await api.get(sentTo).catch((e: unknown) => {
        if (e instanceof Unreachable) return api.get(sentTo);
        throw e;
      });
      const last = updated.turns[updated.turns.length - 1];
      const asks = last ? replyQuestion(last.envelope) : null;
      const said = last
        ? `New reply from ${last.agent_id}: ${OUTCOME[last.envelope.outcome.status].label}.` +
          (asks ? ` It asks you to choose: ${asks.question_prompt}` : "")
        : "";
      announceDrafts.current = last
        ? { said, invocationIds: [last.invocation_id, ...last.children.map((c) => c.invocation_id)] }
        : null;
      setConversation(updated);
      setAnnouncement(said);
      void reloadPast();
      reloadProjects();
    } catch (e) {
      if (stored) {
        void reloadPast();
        reloadProjects();
        setError(
          "Your message was sent and answered, but Data Director could not show the reply " +
            `(${errorMessage(e)}). Open this conversation from Conversations to see it.`,
        );
        setAnnouncement("");
        return;
      }
      if (fromBox) {
        setText(message);
        setAttached(inventory);
        setAttachedDocument(attachedDoc);
      }
      if (e instanceof Unreachable) {
        // The server may have received the turn and be running it, so show what it stored.
        if (id) api.get(id).then(setConversation, () => undefined);
        setError(
          "Data Director could not reach the server, so this message may not have been sent. " +
            "Your message is kept: sending it again is safe, because a message that was " +
            "received is not run twice.",
        );
      } else if (e instanceof TurnConflict) {
        if (id) api.get(id).then(setConversation, () => undefined);
        setError(
          "This conversation has changed since you wrote this: another message was answered or " +
            "is still being answered. Your message is kept. Check the conversation above, then " +
            "send it again if it is still needed.",
        );
      } else {
        setError(
          e instanceof RunRefused
            ? `${e.problem.title}: ${e.message}`
            : `Data Director could not send this: ${errorMessage(e)}`,
        );
      }
      setAnnouncement("");
    } finally {
      setSent(null);
      setBusy(false);
      box.current?.focus();
    }
  }

  function reset() {
    setConversationId(null);
    setConversation(null);
    setOpenProject(undefined);
    handled.current = null;
    if (runId || urlConversation) navigate("/");
    setError(null);
    setText("");
    setAttached(null);
    setAttachedDocument(null);
    setAttachError(null);
    setAnnouncement("");
    box.current?.focus();
  }

  async function reopen(id: string) {
    try {
      const found = await api.get(id);
      handled.current = id;
      setConversation(found);
      setConversationId(id);
      setOpenProject(found.project_id ?? null);
      // A conversation is opened in its own project, so the workspace follows it there.
      if ((found.project_id ?? null) !== projectId) setProjectId(found.project_id ?? null);
      setError(null);
      navigate(homePath({ conversation: id }));
      box.current?.focus();
    } catch (e) {
      setError(`Data Director could not open that conversation: ${errorMessage(e)}`);
    }
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

  // A run named in the address but not in the transcript, as when its conversation is not the one
  // open, is shown above the message box so the link still opens it.
  const inTranscript = conversation?.turns
    .flatMap((t) => t.children)
    .some((c) => c.invocation_id === runId);

  return (
    <Workspace
      {...frame}
      title="Talk to Data Director"
      titleHidden
      centre={
        <section aria-labelledby="conversation-heading" className="conversation-main">
          <h2 id="conversation-heading" className="visually-hidden">
            Conversation
          </h2>
          {((conversation && conversation.turns.length > 0) || sent !== null) && (
            <Transcript
              conversation={conversation}
              agents={directory.agents}
              onToggleRun={toggleRun}
              selectedRun={runId}
              documents={documents.state === "loaded" ? documents.documents : null}
              pending={
                sent === null
                  ? null
                  : {
                      agentId: orchestrator.id,
                      message: sent.message,
                      inventory: sent.inventory,
                      document: sent.document,
                    }
              }
              onAnswer={(answer, message) => void answerQuestion(answer, message)}
              chosenRepository={project?.repository?.re3data_id ?? null}
              {...(projectId
                ? {
                    onDocumentAnswered: (value: ProjectDocuments) =>
                      setDocumentsOf({
                        projectId,
                        read: { state: "loaded", documents: value.documents },
                      }),
                    // The panel reads the choice from the projects list, so it is read again.
                    onRepositoryChosen: () => reloadProjects(),
                  }
                : {})}
            />
          )}
          {runId && !inTranscript && (
            <section aria-labelledby="linked-run" className="callout">
              <h3 id="linked-run">
                Run <code>{runId}</code>
              </h3>
              <RunDetail invocationId={runId} agents={directory.agents} idPrefix="linked-run" />
              <p>
                <Button icon={X} onPress={() => navigate("/")}>Close the run</Button>
              </p>
            </section>
          )}
          {/* Dropping a file is a shortcut for the Attach a file button, which keyboard and
              screen reader users have, so the form's drag listeners need no role of their own. */}
          {/* eslint-disable-next-line jsx-a11y/no-noninteractive-element-interactions */}
          <form
            onSubmit={(e) => void send(e)}
            aria-busy={busy}
            className={dropping ? "dropping" : undefined}
            onDragOver={onDragOver}
            onDragLeave={() => setDropping(false)}
            onDrop={onDrop}
          >
            <div className="field">
              <label htmlFor="message">What would you like to do?</label>
              <textarea
                id="message"
                ref={box}
                rows={3}
                aria-describedby="message-hint"
                value={text}
                onChange={(e) => setText(e.target.value)}
                onPaste={onPaste}
                onKeyDown={(e) => {
                  // Ctrl+Enter (Cmd+Enter on a Mac) sends; the Send button's rules still apply.
                  if (e.key === "Enter" && (e.ctrlKey || e.metaKey) && !e.nativeEvent.isComposing) {
                    e.preventDefault();
                    if (!busy && (text.trim() || attached || attachedDocument)) {
                      e.currentTarget.form?.requestSubmit();
                    }
                  }
                }}
              />
              <p id="message-hint" className="hint">
                Press <kbd>Ctrl</kbd>+<kbd>Enter</kbd> (<kbd>Cmd</kbd>+<kbd>Enter</kbd> on a Mac)
                to send.
              </p>
            </div>
            <div className="composer-attach">
              {attached && (
                <InventoryChip
                  fileCount={attached.fileCount}
                  madeAt={attached.madeAt}
                  name={attached.name}
                  source={{ document: attached.document }}
                  onRemove={removeInventory}
                />
              )}
              {attachedDocument && (
                <DocumentChip
                  name={attachedDocument.name}
                  size={attachedDocument.size}
                  onRemove={removeDocument}
                />
              )}
              {!(attached && attachedDocument) && (
                <FileTrigger
                  acceptedFileTypes={[
                    "application/json",
                    ".json",
                    "text/plain",
                    "text/markdown",
                    ...DOCUMENT_EXTENSIONS,
                  ]}
                  onSelect={(files) => void attachFile(files?.[0])}
                >
                  <Button icon={Paperclip} isDisabled={busy} aria-describedby="attach-hint">
                    Attach a file
                  </Button>
                </FileTrigger>
              )}
              {!attached && (
                <MakeInventoryDialog
                  isDisabled={busy}
                  onAttach={(file) => void attachFromDialog(file)}
                />
              )}
            </div>
            <p id="attach-hint" className="hint">
              Attach an inventory of your data files (.json), which holds their names, sizes,
              formats and table column headings but not the data themselves, or a document about
              your data, such as a protocol or codebook (.txt or .md). Never attach the data
              themselves: your data are not uploaded.
            </p>
            <InventoryReviewDialog
              pending={pending}
              onAttach={confirmInventory}
              onDiscard={discardInventory}
            />
            <DocumentReviewDialog
              pending={pendingDocument}
              onAttach={confirmDocument}
              onDiscard={discardDocument}
            />
            {attachError && (
              <p role="alert" className="callout status-danger">
                {attachError}
              </p>
            )}
            <Button
              type="submit"
              variant="primary"
              icon={SendHorizontal}
              isDisabled={!busy && !text.trim() && !attached && !attachedDocument}
              isPending={busy}
            >
              {busy ? "Sending…" : "Send"}
            </Button>
          </form>
          <div role="status" aria-live="polite" className="visually-hidden">
            {announcement}
          </div>
          {error && (
            <div role="alert" className="callout status-danger">
              <p>{error}</p>
            </div>
          )}
        </section>
      }
      history={
        <EarlierConversations
          conversations={past.filter((c) => (c.project_id ?? null) === projectId)}
          currentId={conversationId}
          onOpen={(id) => void reopen(id)}
          onNew={reset}
        />
      }
      context={<ContextPanel projectId={projectId} project={project} conversation={conversation} documents={documents} />}
    />
  );
}
