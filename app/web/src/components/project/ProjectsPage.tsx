/**
 * The person's projects, the first page in the main navigation (docs/specs/app.md): each project
 * they may read, the one created last first, with what it holds. A project is the unit of work
 * (docs/specs/projects.md), so this page is where the work is organised; a conversation still
 * starts one, so a person never has to make a project before saying what they need.
 *
 * The app starts projects untitled, so a project is named by its first conversation's title, as
 * the harness derives it, or else by when it was started. The app works in one project at a time
 * (docs/specs/app.md): each project here can be opened, which makes it the active one and goes to
 * its conversations, and the active one is marked. Its name links to its documents.
 */

import "./ProjectsPage.css";

import { FolderOpen, FolderPlus } from "lucide-react";
import { useEffect, useState } from "react";

import { useActiveProject } from "../../project/active";
import { type ProjectSummary, useProjectApi } from "../../project/api";
import { day, projectName } from "../../project/name";
import { Link, navigate } from "../../route";
import { PageHeader } from "../frame/PageHeader";
import { Button } from "../ui/Button";

type Load =
  | { state: "loading" }
  | { state: "failed"; message: string }
  | { state: "loaded"; value: ProjectSummary[] };

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

export function ProjectsPage() {
  const api = useProjectApi();
  const [load, setLoad] = useState<Load>({ state: "loading" });
  const { projectId: activeId, setProjectId } = useActiveProject();

  function open(projectId: string | null) {
    setProjectId(projectId);
    navigate("/");
  }

  useEffect(() => {
    const controller = new AbortController();
    api.projects(controller.signal).then(
      (value) => setLoad({ state: "loaded", value }),
      (error: unknown) => {
        if (controller.signal.aborted) return;
        setLoad({ state: "failed", message: error instanceof Error ? error.message : String(error) });
      },
    );
    return () => controller.abort();
  }, [api]);

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
          You have no project yet. Start a new project: your first message in it keeps the
          inventory you attach and the documents agents draft for you.
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
        <Button icon={FolderPlus} onPress={() => open(null)}>
          Start a new project
        </Button>{" "}
        <span className="hint">Your first message in it starts the project.</span>
      </p>
      {content()}
    </>
  );
}
