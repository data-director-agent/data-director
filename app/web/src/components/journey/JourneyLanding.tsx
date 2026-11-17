/**
 * `/journey`, the main navigation's way to the journey map. With a project to work in, it opens
 * that project's map in its place, so Back skips it; with none, it lists the person's projects,
 * each linking to its map. The list is read from the server, so a project remembered by this
 * browser but no longer listed is not opened.
 */

import { FolderPlus } from "lucide-react";
import { useEffect, useState } from "react";

import { useActiveProject } from "../../project/active";
import { type ProjectSummary, useProjectApi } from "../../project/api";
import { projectName } from "../../project/name";
import { errorMessage } from "../../run/api";
import { Link, journeyPath, navigate } from "../../route";
import { PageHeader } from "../frame/PageHeader";

type Load =
  | { state: "loading" }
  | { state: "failed"; message: string }
  | { state: "loaded"; value: ProjectSummary[] };

export function JourneyLanding() {
  const api = useProjectApi();
  const { projectId } = useActiveProject();
  const [load, setLoad] = useState<Load>({ state: "loading" });

  useEffect(() => {
    const controller = new AbortController();
    api.projects(controller.signal).then(
      (value) => setLoad({ state: "loaded", value }),
      (e: unknown) =>
        controller.signal.aborted || setLoad({ state: "failed", message: errorMessage(e) }),
    );
    return () => controller.abort();
  }, [api]);

  const listed = load.state === "loaded" ? load.value : null;
  const opening =
    projectId !== null && listed !== null && listed.some((p) => p.project_id === projectId);
  useEffect(() => {
    if (opening && projectId) navigate(journeyPath(projectId), true);
  }, [opening, projectId]);

  const content = () => {
    if (load.state === "loading" || opening) return <p role="status">Opening the journey map…</p>;
    if (load.state === "failed") {
      return (
        <div role="alert" className="callout status-danger">
          <p>Data Director could not list your projects: {load.message}.</p>
        </div>
      );
    }
    if (load.value.length === 0) {
      return (
        <p>
          The journey map shows where a project is, from planning its data to sharing it. You have
          no project yet.{" "}
          <Link to="/projects">
            <FolderPlus size="1em" aria-hidden="true" /> Start a new project
          </Link>
        </p>
      );
    }
    return (
      <>
        <p>Choose a project to see where it is, from planning its data to sharing it.</p>
        <ul className="plain-list">
          {load.value.map((project) => (
            <li key={project.project_id}>
              <Link to={journeyPath(project.project_id)}>{projectName(project)}</Link>
            </li>
          ))}
        </ul>
      </>
    );
  };

  return (
    <>
      <PageHeader title="Your data journey" />
      {content()}
    </>
  );
}
