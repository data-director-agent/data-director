/**
 * Reading the run store, behind one interface so tests can stand in for the server.
 *
 * The browser starts runs only through conversation turns; `POST /api/runs` is kept for scripting
 * (docs/specs/app.md, "Run events to the browser").
 */

import { createContext, useContext } from "react";

import { checkSignedIn } from "../session/api";
import type { Problem, RunResult, RunRow } from "./types";

/** The server refused the request before any run began (a 400 with Problem Details). */
export class RunRefused extends Error {
  constructor(readonly problem: Problem) {
    super(problem.detail ?? problem.title);
  }
}

export interface RunApi {
  list(signal?: AbortSignal): Promise<RunRow[]>;
  get(invocationId: string, signal?: AbortSignal): Promise<RunResult>;
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
  async list(signal) {
    return json(await fetch("/api/runs", init(signal)));
  },
  async get(invocationId, signal) {
    return json(await fetch(`/api/runs/${encodeURIComponent(invocationId)}`, init(signal)));
  },
};

export const RunApiContext = createContext<RunApi>(httpRunApi);

export function useRunApi(): RunApi {
  return useContext(RunApiContext);
}

export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
