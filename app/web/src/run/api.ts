/**
 * Reading the run store, behind one interface so tests can stand in for the server.
 *
 * The browser starts runs only through conversation turns; `POST /api/runs` is kept for scripting
 * (docs/specs/app.md, "Run events to the browser").
 */

import { createContext, useContext } from "react";

import { json } from "../http";
import type { RunRow, StoredRun } from "./types";

export { RunRefused } from "../http";

export interface RunApi {
  list(signal?: AbortSignal): Promise<RunRow[]>;
  /** A stored run: its envelope, its checks and the request it was started with. */
  get(invocationId: string, signal?: AbortSignal): Promise<StoredRun>;
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
