/**
 * Two pages, `/` (the conversation) and `/agents` (the directory), kept in the address bar with
 * the History API so each can be linked, bookmarked and left with Back. A link is a real `<a>`,
 * so opening it in a new tab works; a plain click is handled in the page.
 */

import { type MouseEvent, type ReactNode, createElement, useSyncExternalStore } from "react";

const CHANGED = "dd-navigate";

function subscribe(listener: () => void): () => void {
  window.addEventListener("popstate", listener);
  window.addEventListener(CHANGED, listener);
  return () => {
    window.removeEventListener("popstate", listener);
    window.removeEventListener(CHANGED, listener);
  };
}

/** The current path and query, e.g. `/agents?agent=example.hello`. */
export function useLocation(): string {
  return useSyncExternalStore(subscribe, () => location.pathname + location.search);
}

/** Moves to `to`; with `replace` the current history entry is replaced, so Back skips it. */
export function navigate(to: string, replace = false): void {
  if (replace) history.replaceState(null, "", to);
  else history.pushState(null, "", to);
  window.dispatchEvent(new Event(CHANGED));
}

/** The conversation page's address: the open conversation (`?conversation=`), the run shown
 * (`?run=`), a step of the journey to ask about (`?ask=`) and a draft's question to talk through
 * (`?question=`, as `{document_id}/{question_id}`), each left out when none. */
export function homePath({
  conversation,
  run,
  ask,
  question,
}: {
  conversation?: string | null;
  run?: string | null;
  ask?: string | null;
  question?: string | null;
}): string {
  const query = new URLSearchParams();
  if (conversation) query.set("conversation", conversation);
  if (run) query.set("run", run);
  if (ask) query.set("ask", ask);
  if (question) query.set("question", question);
  const text = query.toString();
  return text ? `/?${text}` : "/";
}

/** A project's pages, each a tab (docs/specs/app.md): its documents at `/projects/{id}`, and each
 * other at `/projects/{id}/{tab}`. */
export const PROJECT_TABS = [
  "documents",
  "researchers",
  "facts",
  "repository",
  "ai-use",
  "deposit",
  "journey",
] as const;
export type ProjectTab = (typeof PROJECT_TABS)[number];

export function isProjectTab(value: string): value is ProjectTab {
  return (PROJECT_TABS as readonly string[]).includes(value);
}

/** A project's page: its documents, or the tab given. */
export function projectTabPath(projectId: string, tab: ProjectTab = "documents"): string {
  const base = `/projects/${encodeURIComponent(projectId)}`;
  return tab === "documents" ? base : `${base}/${tab}`;
}

/** A project's journey map, with a step open (`?step=`) when one is given. */
export function journeyPath(projectId: string, step?: string | null): string {
  const base = projectTabPath(projectId, "journey");
  return step ? `${base}?step=${encodeURIComponent(step)}` : base;
}

export function Link({
  to,
  children,
  ...rest
}: {
  to: string;
  children: ReactNode;
  className?: string;
  "aria-current"?: "page";
  "aria-label"?: string;
}) {
  return createElement(
    "a",
    {
      href: to,
      ...rest,
      onClick: (event: MouseEvent) => {
        if (event.defaultPrevented || event.button !== 0) return;
        if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
        event.preventDefault();
        navigate(to);
      },
    },
    children,
  );
}
