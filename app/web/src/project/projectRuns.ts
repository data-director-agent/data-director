/**
 * A project's runs whose payload is of one class, newest first (`GET /api/projects/{id}/runs`,
 * docs/specs/app.md), behind one interface so tests can stand in for the server. The shell names
 * the class, as it recognises a payload by its class and never by the agent that ran it.
 */

import { createContext, useContext } from "react";

import type { ProjectRuns } from "../api/generated/responses";
import { json } from "../http";

export interface ProjectRunsApi {
  runs(
    projectId: string,
    payloadClass: string,
    signal?: AbortSignal,
  ): Promise<ProjectRuns>;
}

export const httpProjectRunsApi: ProjectRunsApi = {
  async runs(projectId, payloadClass, signal) {
    const query = new URLSearchParams({ payload: payloadClass });
    const path = `/api/projects/${encodeURIComponent(projectId)}/runs?${query.toString()}`;
    return json<ProjectRuns>(await fetch(path, signal ? { signal } : {}));
  },
};

export const ProjectRunsApiContext =
  createContext<ProjectRunsApi>(httpProjectRunsApi);

export function useProjectRunsApi(): ProjectRunsApi {
  return useContext(ProjectRunsApiContext);
}
