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

export function navigate(to: string): void {
  history.pushState(null, "", to);
  window.dispatchEvent(new Event(CHANGED));
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
