/**
 * A project's documents, each with its latest version and, while that version is undecided, the
 * form to approve it, edit then approve it, or reject it (docs/specs/projects.md).
 *
 * The page draws what the server reads back from the project log, and nothing it inferred: after
 * a decision it shows the state the server answered with, and after a refusal it reads the
 * project again, keeping what it showed if that read fails. What a decision did is said once, in the page's live region, which is in the
 * page from the start so that a screen reader announces each change to it.
 */

import "./ProjectPage.css";

import { useCallback, useEffect, useRef, useState } from "react";

import { type ProjectDocuments, useProjectApi } from "../../project/api";
import { Link } from "../../route";
import { PageHeader } from "../frame/PageHeader";
import { DisclosurePanel } from "./DisclosurePanel";
import { DocumentReview } from "./DocumentReview";

type Load =
  | { state: "loading" }
  | { state: "failed"; message: string }
  | { state: "loaded"; value: ProjectDocuments };

function message(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

export function ProjectPage({ projectId }: { projectId: string }) {
  const api = useProjectApi();
  const [load, setLoad] = useState<Load>({ state: "loading" });
  const [announcement, setAnnouncement] = useState("");
  // Counts what the page has read, so that the disclosure is read again after a decision.
  const [revision, setRevision] = useState(0);

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

  // A link to one document (`#document-{id}`, as the conversation's cards and side bar give)
  // takes the person to it once the page has first been read: its heading is scrolled to and
  // focused, so that a screen reader starts there too.
  const arrived = useRef(false);
  useEffect(() => {
    if (load.state !== "loaded" || arrived.current) return;
    arrived.current = true;
    const target = decodeURIComponent(window.location.hash.slice(1));
    if (!target) return;
    const heading = window.document.getElementById(target)?.querySelector<HTMLElement>("h2");
    heading?.scrollIntoView?.({ block: "start" });
    heading?.focus();
  }, [load]);

  // After a refusal: the documents already shown stay if the project cannot be read again, so
  // that the person still sees why their decision was refused. Answers what went wrong, if
  // anything.
  const refresh = useCallback(
    () =>
      api.documents(projectId).then(
        (value) => {
          setLoad({ state: "loaded", value });
          setRevision((n) => n + 1);
          return null;
        },
        (error: unknown) => message(error),
      ),
    [api, projectId],
  );

  const decided = useCallback((value: ProjectDocuments, said: string) => {
    setLoad({ state: "loaded", value });
    setAnnouncement(said);
    setRevision((n) => n + 1);
  }, []);

  const content = () => {
    if (load.state === "loading") return <p>Reading the project…</p>;
    if (load.state === "failed") {
      return (
        <div role="alert" className="callout status-danger">
          <p>Data Director could not read this project: {load.message}</p>
        </div>
      );
    }
    const { documents, review } = load.value;
    if (documents.length === 0) {
      return (
        <p>
          No document has been drafted for this project yet. Each draft an agent makes is listed
          here for you to check.
        </p>
      );
    }
    return (
      <>
        {documents.map((document) => (
          <DocumentReview
            key={document.document_id}
            projectId={projectId}
            document={document}
            rules={review}
            onDecided={decided}
            onStale={refresh}
          />
        ))}
        <DisclosurePanel projectId={projectId} revision={revision} />
      </>
    );
  };

  return (
    <>
      <p>
        <Link to="/projects">All projects</Link>
      </p>
      <PageHeader title="Project documents">
        <p className="hint">
          Check each draft before it goes into the deposit package. Approve it as it is, edit it
          and approve your version, or reject it. A decision cannot be changed once it is made;
          a newer version can be.
        </p>
      </PageHeader>
      <div role="status" className={announcement ? "callout status-ok" : undefined}>
        {announcement && <p>{announcement}</p>}
      </div>
      {content()}
    </>
  );
}
