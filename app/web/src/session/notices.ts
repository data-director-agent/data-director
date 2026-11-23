/**
 * What data stewards have done in the person's projects lately (`GET /api/notices`,
 * docs/specs/stewardship.md, invariant 13): a steward asked them something, resolved or handed
 * back a request, wrote to them, or a request was sent to its team again. The deployment holds no
 * email address for a researcher, so these are read here, in the banner.
 *
 * Which notices the person has seen, and which kinds they want shown, are kept in this browser
 * only, as the preferences are (`preferences.ts`): nothing about them reaches the server. Storage
 * can be unavailable, so every read and write tolerates failure: then nothing is remembered as
 * seen, and every kind is shown.
 */

import { useSyncExternalStore } from "react";

import type { Notice, Notices } from "../api/generated/responses";
import { json } from "../http";

export type { Notice } from "../api/generated/responses";

export type NoticeKind = Notice["kind"];

/** Every kind, in the order the Settings page lists them, with what each is called there. */
export const NOTICE_KINDS: readonly { kind: NoticeKind; label: string }[] = [
  { kind: "waiting", label: "A data steward asks you something" },
  { kind: "message", label: "A data steward writes to you" },
  { kind: "resolved", label: "A data steward resolves your request" },
  { kind: "handed_back", label: "A data steward hands your request back" },
  { kind: "rerouted", label: "Your request is sent to the team again, as nobody had taken it" },
];

const SEEN_KEY = "dd-notices-seen";
const HIDDEN_KEY = "dd-notices-hidden";
// Enough for a month of notices in a busy project; the oldest are forgotten first.
const SEEN_LIMIT = 500;

export async function fetchNotices(signal?: AbortSignal): Promise<Notice[]> {
  const found = await json<Notices>(await fetch("/api/notices", signal ? { signal } : {}));
  return found.notices;
}

function readList(key: string): string[] {
  try {
    const value: unknown = JSON.parse(localStorage.getItem(key) ?? "[]");
    return Array.isArray(value) ? value.filter((v): v is string => typeof v === "string") : [];
  } catch {
    return [];
  }
}

function writeList(key: string, values: readonly string[]): void {
  try {
    localStorage.setItem(key, JSON.stringify(values));
  } catch {
    // Not remembered; the page goes on.
  }
  for (const listener of listeners) listener();
}

const listeners = new Set<() => void>();

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  const onStorage = (event: StorageEvent) => {
    if (event.key === null || event.key === SEEN_KEY || event.key === HIDDEN_KEY) listener();
  };
  window.addEventListener("storage", onStorage);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", onStorage);
  };
}

interface NoticeChoices {
  seen: ReadonlySet<string>;
  hidden: ReadonlySet<NoticeKind>;
}

let snapshot: NoticeChoices = { seen: new Set(), hidden: new Set() };
let snapshotText = "";

function getSnapshot(): NoticeChoices {
  const seen = readList(SEEN_KEY);
  const hidden = readList(HIDDEN_KEY);
  const text = JSON.stringify([seen, hidden]);
  // The same object while nothing changed, as `useSyncExternalStore` requires.
  if (text !== snapshotText) {
    snapshotText = text;
    snapshot = { seen: new Set(seen), hidden: new Set(hidden as NoticeKind[]) };
  }
  return snapshot;
}

const EMPTY: NoticeChoices = { seen: new Set(), hidden: new Set() };

/** The notices seen and the kinds hidden, re-rendering the caller when either changes. */
export function useNoticeChoices(): NoticeChoices {
  return useSyncExternalStore(subscribe, getSnapshot, () => EMPTY);
}

/** Remembers `notices` as seen. */
export function markSeen(notices: readonly Notice[]): void {
  const seen = readList(SEEN_KEY);
  const fresh = notices.map((n) => n.event_id).filter((id) => !seen.includes(id));
  if (fresh.length > 0) writeList(SEEN_KEY, [...seen, ...fresh].slice(-SEEN_LIMIT));
}

/** Shows or hides one kind of notice. */
export function setShown(kind: NoticeKind, shown: boolean): void {
  const hidden = readList(HIDDEN_KEY).filter((k) => k !== kind);
  writeList(HIDDEN_KEY, shown ? hidden : [...hidden, kind]);
}

/** The notices of the kinds the person wants shown. */
export function shownNotices(notices: readonly Notice[], choices: NoticeChoices): Notice[] {
  return notices.filter((n) => !choices.hidden.has(n.kind));
}

/** How many of the shown notices the person has not seen. */
export function unseenCount(notices: readonly Notice[], choices: NoticeChoices): number {
  return shownNotices(notices, choices).filter((n) => !choices.seen.has(n.event_id)).length;
}
