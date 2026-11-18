/**
 * `/project`, the main navigation's way to a project. With a project to work in, it opens that
 * project's page (`/projects/{project_id}`) in its place, so Back skips it; with none, it opens
 * the list of the person's projects (`/projects`), where one can be chosen or started. The list
 * is read from the server, so a project remembered by this browser but no longer listed is not
 * opened.
 */

import { useEffect, useState } from "react";

import { useActiveProject } from "../../project/active";
import { useProjectApi } from "../../project/api";
import { navigate } from "../../route";
import { projectPath } from "./ProjectNav";

export function ProjectLanding() {
  const api = useProjectApi();
  const { projectId } = useActiveProject();
  const [listed, setListed] = useState<string[] | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    // Whether the read succeeds or not, the list page is where to go without a project; it says
    // for itself when it cannot list them.
    api.projects(controller.signal).then(
      (value) => setListed(value.map((p) => p.project_id)),
      () => controller.signal.aborted || setListed([]),
    );
    return () => controller.abort();
  }, [api]);

  useEffect(() => {
    if (listed === null) return;
    if (projectId !== null && listed.includes(projectId)) navigate(projectPath(projectId), true);
    else navigate("/projects", true);
  }, [listed, projectId]);

  return <p role="status">Opening your project…</p>;
}
