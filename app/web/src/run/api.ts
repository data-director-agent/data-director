/**
 * The run endpoints, behind one interface so tests can stand in for the server.
 *
 * `POST /api/runs` answers when the run has ended: the page learns nothing while it runs. A
 * stopgap until runs stream over AG-UI (#68, #69).
 */

import { createContext, useContext } from "react";

import { checkSignedIn } from "../session/api";
import type { Example, Problem, RunResult, RunRow } from "./types";

/** The server refused the request before any run began (a 400 with Problem Details). */
export class RunRefused extends Error {
  constructor(readonly problem: Problem) {
    super(problem.detail ?? problem.title);
  }
}

export interface RunApi {
  start(agentId: string, input: Record<string, unknown>, signal?: AbortSignal): Promise<RunResult>;
  list(signal?: AbortSignal): Promise<RunRow[]>;
  get(invocationId: string, signal?: AbortSignal): Promise<RunResult>;
  examples(signal?: AbortSignal): Promise<Example[]>;
}

async function json<T>(response: Response): Promise<T> {
  checkSignedIn(response);
  if (response.status === 400) throw new RunRefused((await response.json()) as Problem);
  if (!response.ok) throw new Error(`the server answered ${response.status}`);
  return (await response.json()) as T;
}

function init(signal?: AbortSignal): RequestInit {
  return signal ? { signal } : {};
}

export const httpRunApi: RunApi = {
  async start(agentId, input, signal) {
    return json(
      await fetch("/api/runs", {
        ...init(signal),
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ agent_id: agentId, input }),
      }),
    );
  },
  async list(signal) {
    return json(await fetch("/api/runs", init(signal)));
  },
  async get(invocationId, signal) {
    return json(await fetch(`/api/runs/${encodeURIComponent(invocationId)}`, init(signal)));
  },
  async examples(signal) {
    return json(await fetch("/api/examples", init(signal)));
  },
};

export const RunApiContext = createContext<RunApi>(httpRunApi);

export function useRunApi(): RunApi {
  return useContext(RunApiContext);
}

export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
