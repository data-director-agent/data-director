/**
 * A project's documents (docs/specs/projects.md), as a list beside a reader: the list groups the
 * documents by state, those waiting for a decision first, and the reader shows the one chosen,
 * with the form to decide on it while it is undecided. The researchers, the project's facts, the
 * repository chosen, the statement of how generative AI was used and the deposit package each
 * have a tab of their own (`ProjectPanelPage`); an old link to one of them here (`?doc=repository`
 * and the like) is sent on to its tab.
 *
 * What is open is in the address (`?doc=<id>`, and `&v=<n>` for an earlier version), so that it
 * can be linked and left with Back. With nothing chosen, the first document waiting for a decision
 * opens, or else the first document. On a narrow screen the list and the reader take turns: the
 * list until a document is chosen, then the reader with a link back to the list.
 *
 * The page draws what the server reads back from the project log, and nothing it inferred: after
 * a decision it shows the state the server answered with, and after a refusal it reads the
 * project again, keeping what it showed if that read fails. What a decision did is said once, in
 * the page's live region, which is in the page from the start so that a screen reader announces
 * each change to it; it offers the next document waiting for a decision, without moving to it.
 *
 * The header offers to rename the project (`ProjectRename`); after a rename the page reads the
 * project's name again rather than showing the one it sent.
 *
 * A project the page could read becomes the one the app is working in (docs/specs/app.md), so a
 * link to it lands in that project. The project's conversations are listed beneath its documents
 * (`ProjectConversations`), each one press away, with a link to start a new one; on a narrow
 * screen they take turns with the reader as the documents do.
 */

import "./ProjectPage.css";

import { ArrowLeft } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { useActiveProject } from "../../project/active";
import {
  type DocumentVersion,
  type ProjectDocuments,
  type ProjectSummary,
  useProjectApi,
} from "../../project/api";
import { deletionName, documentName, projectName } from "../../project/name";
import { Link, navigate, projectTabPath } from "../../route";
import { AddInventory } from "../inventory/AddInventory";
import { PageHeader } from "../frame/PageHeader";
import { PageLoading } from "../ui/PageLoading";
import { DocumentList, FORMER_PANELS, stateOf } from "./DocumentList";
import { DeleteProject } from "./DeleteProject";
import { DocumentReader } from "./DocumentReader";
import { ProjectConversations } from "./ProjectConversations";
import { ProjectNav } from "./ProjectNav";
import { ProjectRename } from "./ProjectRename";

type Load =
  | { state: "loading" }
  | { state: "failed"; message: string }
  | { state: "loaded"; value: ProjectDocuments };

function message(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

/** Whether the project's name and its documents have both been read, or failed to be. */
function bothRead(named: boolean, load: Load): boolean {
  return named && load.state !== "loading";
}

/** The version asked for, if `v` is a whole number. */
function versionOf(v: string | null): number | null {
  return v !== null && /^\d+$/.test(v) ? Number(v) : null;
}

export function ProjectPage({ projectId, query = "" }: { projectId: string; query?: string }) {
  const api = useProjectApi();
  const [load, setLoad] = useState<Load>({ state: "loading" });
  const [project, setProject] = useState<ProjectSummary | null>(null);
  // Whether the first read of the project's name has landed or failed.
  const [named, setNamed] = useState(false);
  // Counts renames, so that the project's name is read again after one.
  const [renamed, setRenamed] = useState(0);
  // What a decision did, said while the document it was made on is open (`on`, as asked).
  const [decision, setDecision] = useState<{
    said: string;
    next: string | null;
    on: string | null;
  } | null>(null);
  const { setProjectId } = useActiveProject();
  const readable = load.state === "loaded";

  useEffect(() => {
    if (readable) setProjectId(projectId);
  }, [readable, projectId, setProjectId]);

  const params = new URLSearchParams(query);
  const asked = params.get("doc");
  const moved = asked === null ? undefined : FORMER_PANELS[asked];

  // What was once a panel here is a tab now: an old link lands on it, and Back skips this one.
  useEffect(() => {
    if (moved) navigate(projectTabPath(projectId, moved), true);
  }, [moved, projectId]);
  const shown = versionOf(params.get("v"));
  const base = `/projects/${encodeURIComponent(projectId)}`;
  const hrefFor = (id: string, version?: number) =>
    `${base}?doc=${encodeURIComponent(id)}${version === undefined ? "" : `&v=${version}`}`;

  const read = useCallback(
    (signal?: AbortSignal) =>
      api.documents(projectId, signal).then(
        (value) => setLoad({ state: "loaded", value }),
        (error: unknown) => {
          if (!signal?.aborted) setLoad({ state: "failed", message: message(error) });
        },
      ),
    [api, projectId],
  );

  useEffect(() => {
    const controller = new AbortController();
    void read(controller.signal);
    return () => controller.abort();
  }, [read]);

  // The project's name is a nicety: while it is read, or if it cannot be, the page says what it is.
  useEffect(() => {
    const controller = new AbortController();
    api.projects(controller.signal).then(
      (projects) => {
        const found = projects.find((p) => p.project_id === projectId);
        if (found) setProject(found);
        setNamed(true);
      },
      () => {
        if (!controller.signal.aborted) setNamed(true);
      },
    );
    return () => controller.abort();
  }, [api, projectId, renamed]);
  const title = project ? projectName(project) : null;

  // After a refusal: the documents already shown stay if the project cannot be read again, so
  // that the person still sees why their decision was refused. Answers what went wrong, if
  // anything.
  const refresh = useCallback(
    () =>
      api.documents(projectId).then(
        (value) => {
          setLoad({ state: "loaded", value });
          return null;
        },
        (error: unknown) => message(error),
      ),
    [api, projectId],
  );

  const decided = (value: ProjectDocuments, said: string) => {
    setLoad({ state: "loaded", value });
    const next = value.documents.find(
      (document) =>
        stateOf(document) === "proposed" && document.document_id !== value.decided?.document_id,
    );
    setDecision({ said, next: next ? next.document_id : null, on: asked });
  };

  // After answers: the page draws what the server read back; focus stays in the form, whose
  // status says how many were recorded.
  const answered = (value: ProjectDocuments) => setLoad({ state: "loaded", value });

  const content = () => {
    if (load.state === "loading") return <p role="status">Reading the project…</p>;
    if (load.state === "failed") {
      return (
        <div role="alert" className="callout status-danger">
          <p>Data Director could not read this project: {load.message}</p>
        </div>
      );
    }
    const { documents, review, answer_max_length: answerMaxLength } = load.value;
    const fallback = documents.find((document) => stateOf(document) === "proposed") ?? documents[0];
    const chosen = asked ?? fallback?.document_id ?? null;
    const document = documents.find((d) => d.document_id === chosen);
    const unknown = chosen !== null && !document;

    const reader = () => {
      if (chosen === null) {
        return (
          <p>
            No document has been drafted for this project yet. Each draft an agent makes is listed
            here for you to check.
          </p>
        );
      }
      if (!document) {
        return (
          <div className="callout status-warn">
            <p>That document is not in this project. Choose one from the list.</p>
          </div>
        );
      }
      return (
        <DocumentReader
          key={document.document_id}
          projectId={projectId}
          document={document}
          shown={shown}
          rules={review}
          answerMaxLength={answerMaxLength}
          hrefFor={(version?: DocumentVersion) => hrefFor(document.document_id, version?.version)}
          onDecided={decided}
          onAnswered={answered}
          onStale={refresh}
        />
      );
    };

    return (
      <div className="document-browser" data-open={asked && !unknown ? "reader" : "list"}>
        <div className="document-browser-side">
          <DocumentList documents={documents} selected={chosen} hrefFor={(id) => hrefFor(id)} />
          <ProjectConversations key={projectId} projectId={projectId} />
        </div>
        <div className="document-browser-reader">
          <p className="document-browser-back">
            <Link to={base}>
              <ArrowLeft size="1em" aria-hidden="true" /> All documents
            </Link>
          </p>
          {reader()}
        </div>
      </div>
    );
  };

  const announcement = decision && decision.on === asked ? decision : null;
  const next =
    announcement?.next && load.state === "loaded"
      ? load.value.documents.find((document) => document.document_id === announcement.next)
      : undefined;

  // Drawn whole once both reads have landed, so that the name and its buttons do not arrive
  // above the documents after they can be pressed (#1328).
  return (
    <PageLoading ready={bothRead(named, load)} said="Reading the project…">
      <>
        <ProjectNav projectId={projectId} name={title} current="documents" />
        <PageHeader title={title ?? "Project documents"}>
          {project && title && (
            <p className="project-name-actions">
              <ProjectRename
                projectId={projectId}
                name={project.title ?? title}
                named={project.title_source ?? null}
                onRenamed={() => setRenamed((n) => n + 1)}
              />{" "}
              <DeleteProject
                projectId={projectId}
                name={title}
                typedName={deletionName(project)}
                restoreDays={project.restore_days}
              />
            </p>
          )}
          <p className="project-inventory-actions">
            <AddInventory
              projectId={projectId}
              replacing={project?.inventory != null}
              onSaved={(saved) => {
                setProject((p) => (p ? { ...p, inventory: saved } : p));
              }}
            />
          </p>
          <p className="hint">
            Check each draft before it goes into the deposit package. Approve it as it is, edit it and
            approve your version, or reject it. A decision cannot be changed once it is made; a newer
            version can be.
          </p>
        </PageHeader>
        <div role="status" className={announcement ? "callout status-ok" : undefined}>
          {announcement && (
            <p>
              {announcement.said}
              {next && (
                <>
                  {" "}
                  Next to review: <Link to={hrefFor(next.document_id)}>{documentName(next)}</Link>
                </>
              )}
            </p>
          )}
        </div>
        {content()}
      </>
    </PageLoading>
  );
}
