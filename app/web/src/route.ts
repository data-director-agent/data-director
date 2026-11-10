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

/** The conversation page's address: the open conversation (`?conversation=`) and the run shown
 * (`?run=`), each left out when none. */
export function homePath({
  conversation,
  run,
}: {
  conversation?: string | null;
  run?: string | null;
}): string {
  const query = new URLSearchParams();
  if (conversation) query.set("conversation", conversation);
  if (run) query.set("run", run);
  const text = query.toString();
  return text ? `/?${text}` : "/";
}

export function Link({
  to,
  children,
  ...rest
}: { to: string; children: ReactNode; className?: string; "aria-current"?: "page" }) {
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
