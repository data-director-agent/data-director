/**
 * The person's projects, the first page in the main navigation (docs/specs/app.md): each project
 * they may read, the one created last first, with what it holds. A project is the unit of work
 * (docs/specs/projects.md), so this page is where the work is organised. **New project** opens a
 * dialog that creates one (docs/specs/app.md, rule 27) and goes to its workspace, where Data
 * Director asks its intake questions first.
 *
 * The app starts projects untitled, so a project is named by its first conversation's title, as
 * the harness derives it, or else by when it was started. The app works in one project at a time
 * (docs/specs/app.md): each project here can be opened, which makes it the active one and goes to
 * its conversations, and the active one is marked. Its name links to its documents.
 *
 * Below them, "Recently deleted" lists the projects the person deleted and may still restore,
 * with when and by whom each was deleted and until when it can be restored
 * (docs/specs/projects.md, invariants 23 and 25). It is not shown while there are none.
 */

import "./ProjectsPage.css";

import { FolderOpen, FolderPlus, RotateCcw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { journey } from "../../flow/journey";
import { useFlowApi } from "../../flow/api";
import type { ProcessFlow, ProjectProgress } from "../../flow/types";
import { useActiveProject } from "../../project/active";
import { type DeletedProject, type ProjectSummary, useProjectApi } from "../../project/api";
import { day, projectName } from "../../project/name";
import { Link, navigate } from "../../route";
import { PageHeader } from "../frame/PageHeader";
import { Button } from "../ui/Button";
import { JourneyMini } from "../journey/JourneyMini";
import { NewProjectDialog } from "./NewProjectDialog";

// Each project as the server lists it, with where it is in the process flow.
type Listed = ProjectSummary & { progress?: ProjectProgress };

type Load =
  | { state: "loading" }
  | { state: "failed"; message: string }
  | { state: "loaded"; value: Listed[] };

function plural(n: number, one: string, many: string): string {
  return `${n} ${n === 1 ? one : many}`;
}

function Holds({ project }: { project: ProjectSummary }) {
  const { inventory, conversations } = project;
  return (
    <p className="hint">
      Started {day(project.created_at)} ·{" "}
      {inventory ? `Inventory of ${plural(inventory.file_count, "file", "files")}` : "No inventory yet"}{" "}
      · {plural(conversations.length, "conversation", "conversations")}
    </p>
  );
}

function Documents({ counts }: { counts: ProjectSummary["documents"] }) {
  if (counts.proposed + counts.approved + counts.rejected === 0) {
    return <p className="hint">No document drafted yet.</p>;
  }
  return (
    <p className="project-card-documents">
      {counts.proposed > 0 && (
        <span className="status status-warn">{counts.proposed} to review</span>
      )}
      {counts.approved > 0 && <span className="status status-ok">{counts.approved} approved</span>}
      {counts.rejected > 0 && (
        <span className="status status-danger">{counts.rejected} rejected</span>
      )}
    </p>
  );
}

function message(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

/** The deleted projects the person may restore; nothing at all while there are none. */
function RecentlyDeleted({
  deleted,
  onRestored,
}: {
  deleted: DeletedProject[];
  onRestored: () => void;
}) {
  const api = useProjectApi();
  const [restoring, setRestoring] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  if (deleted.length === 0) return null;

  const restore = (projectId: string) => {
    setRestoring(projectId);
    setError(null);
    api.restore(projectId).then(
      () => {
        setRestoring(null);
        onRestored();
      },
      (e: unknown) => {
        setRestoring(null);
        setError(`Data Director could not restore this project: ${message(e)}`);
      },
    );
  };

  return (
    <section aria-labelledby="recently-deleted" className="recently-deleted">
      <h2 id="recently-deleted">Recently deleted</h2>
      <p className="hint">
        A deleted project is hidden, not erased. You can restore it, as it was, until the date
        shown.
      </p>
      {error && (
        <div role="alert" className="callout status-danger">
          <p>{error}</p>
        </div>
      )}
      <ul className="plain-list project-list">
        {deleted.map((project) => {
          const name = project.title ?? `Project started ${day(project.created_at)}`;
          return (
            <li key={project.project_id} className="project-card">
              <h3 className="project-card-name">{name}</h3>
              <p className="hint">
                Deleted {day(project.deleted.at)} by {project.deleted.by.name} · Restorable until{" "}
                {day(project.deleted.restorable_until)}
              </p>
              <p>
                <Button
                  icon={RotateCcw}
                  size="small"
                  variant="secondary"
                  isDisabled={restoring !== null}
                  onPress={() => restore(project.project_id)}
                  aria-label={`Restore ${name}`}
                >
                  {restoring === project.project_id ? "Restoring…" : "Restore"}
                </Button>
              </p>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

export function ProjectsPage() {
  const api = useProjectApi();
  const [load, setLoad] = useState<Load>({ state: "loading" });
  const [deleted, setDeleted] = useState<DeletedProject[]>([]);
  const { projectId: activeId, setProjectId, reloadProjects } = useActiveProject();
  const [creating, setCreating] = useState(false);
  const [generation, setGeneration] = useState(0);
  // The process flow, for each card's journey at a glance; without it the cards have none.
  const flowApi = useFlowApi();
  const [flow, setFlow] = useState<ProcessFlow | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    flowApi.get(controller.signal).then(setFlow, () => undefined);
    return () => controller.abort();
  }, [flowApi]);

  function open(projectId: string) {
    setProjectId(projectId);
    navigate("/");
  }

  useEffect(() => {
    const controller = new AbortController();
    api.projects(controller.signal).then(
      (value) => setLoad({ state: "loaded", value }),
      (error: unknown) => {
        if (controller.signal.aborted) return;
        setLoad({ state: "failed", message: message(error) });
      },
    );
    // The deleted projects are a nicety: if they cannot be read, the page lists none.
    api.deletedProjects(controller.signal).then(setDeleted, () => undefined);
    return () => controller.abort();
  }, [api, generation]);

  const restored = useCallback(() => {
    setGeneration((n) => n + 1);
    reloadProjects();
  }, [reloadProjects]);

  const content = () => {
    if (load.state === "loading") return <p role="status">Reading your projects…</p>;
    if (load.state === "failed") {
      return (
        <div role="alert" className="callout status-danger">
          <p>Data Director could not list your projects: {load.message}</p>
        </div>
      );
    }
    if (load.value.length === 0) {
      return (
        <p>
          You have no project yet. Start a new project: it keeps the inventory you attach and the
          documents agents draft for you.
        </p>
      );
    }
    return (
      <ul className="plain-list project-list">
        {load.value.map((project) => {
          const active = project.project_id === activeId;
          const name = projectName(project);
          return (
            <li
              key={project.project_id}
              className={active ? "project-card project-card-active" : "project-card"}
              {...(active ? { "aria-current": "true" as const } : {})}
            >
              <h2 className="project-card-name">
                <Link to={`/projects/${encodeURIComponent(project.project_id)}`}>{name}</Link>
                {active && <span className="status status-ok">Current project</span>}
              </h2>
              {flow && project.progress && (
                <JourneyMini
                  projectId={project.project_id}
                  lines={journey(flow, project.progress)}
                  flow={flow}
                  progress={project.progress}
                />
              )}
              <Holds project={project} />
              <Documents counts={project.documents} />
              <p>
                <Button
                  icon={FolderOpen}
                  size="small"
                  onPress={() => open(project.project_id)}
                  aria-label={`Open the conversations of ${name}`}
                >
                  Open conversations
                </Button>
              </p>
            </li>
          );
        })}
      </ul>
    );
  };

  return (
    <>
      <PageHeader title="Projects">
        <p className="hint">
          Each project keeps one dataset&apos;s inventory, the documents drafted for it and your
          decisions on them.
        </p>
      </PageHeader>
      <p>
        <Button icon={FolderPlus} onPress={() => setCreating(true)}>
          Start a new project
        </Button>{" "}
        <span className="hint">Data Director asks a few questions to place it in the process.</span>
      </p>
      <NewProjectDialog isOpen={creating} onOpenChange={setCreating} />
      {content()}
      <RecentlyDeleted deleted={deleted} onRestored={restored} />
    </>
  );
}
