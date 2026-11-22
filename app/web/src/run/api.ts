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

/** A page of the stored runs, newest first, and the cursor for the next, older one. */
export interface RunPage {
  items: RunRow[];
  /** The `before` cursor of the next page; null on the last. */
  next: string | null;
}

export interface RunApi {
  /** The stored runs the person may read, newest first; `before` names a page after the first. */
  list(before?: string | null, signal?: AbortSignal): Promise<RunPage>;
  /** A stored run: its envelope, its checks and the request it was started with. */
  get(invocationId: string, signal?: AbortSignal): Promise<StoredRun>;
}

function init(signal?: AbortSignal): RequestInit {
  return signal ? { signal } : {};
}

export const httpRunApi: RunApi = {
  async list(before, signal) {
    const query = before ? `?${new URLSearchParams({ before }).toString()}` : "";
    const response = await fetch(`/api/runs${query}`, init(signal));
    const items = await json<RunRow[]>(response);
    return { items, next: nextCursor(response.headers.get("Link")) };
  },
  async get(invocationId, signal) {
    return json(await fetch(`/api/runs/${encodeURIComponent(invocationId)}`, init(signal)));
  },
};

/** The `before` cursor of the `rel="next"` page in a `Link` header, if it names one. */
export function nextCursor(link: string | null): string | null {
  const next = link?.split(",").find((part) => /;\s*rel="?next"?/.test(part));
  const url = next?.match(/<([^>]*)>/)?.[1];
  if (!url) return null;
  return new URL(url, "http://link.invalid").searchParams.get("before");
}

export const RunApiContext = createContext<RunApi>(httpRunApi);

export function useRunApi(): RunApi {
  return useContext(RunApiContext);
}

export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
