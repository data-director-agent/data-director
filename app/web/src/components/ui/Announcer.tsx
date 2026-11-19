/**
 * The page's two live regions, and the one way to speak through them (#948).
 *
 * The frame mounts `AnnouncerProvider` once, so both regions are in the page from load: a polite
 * one (`aria-live="polite"`, `aria-atomic="false"`) for progress and an assertive one for errors.
 * Components call `useAnnounce()`; nothing else sets `aria-live` (a lint rule in
 * eslint.config.js). A message is added as a new entry, so saying the same thing twice is heard
 * twice, and only the last few entries are kept. Both are logs, told apart by name: an empty
 * `alert` in every page would be confused with the page's own error callouts.
 */

import { type ReactNode, createContext, useCallback, useContext, useState } from "react";

export type Announce = (message: string, options?: { assertive?: boolean }) => void;

const AnnounceContext = createContext<Announce | null>(null);

/** How many entries each region keeps: enough to read back, few enough to stay small. */
const KEPT = 5;

interface Entry {
  id: number;
  message: string;
}

let nextId = 0;

function keep(entries: Entry[], message: string): Entry[] {
  nextId += 1;
  return [...entries, { id: nextId, message }].slice(-KEPT);
}

export function AnnouncerProvider({ children }: { children: ReactNode }) {
  const [polite, setPolite] = useState<Entry[]>([]);
  const [assertive, setAssertive] = useState<Entry[]>([]);
  const announce = useCallback<Announce>((message, { assertive: urgent = false } = {}) => {
    if (!message) return;
    (urgent ? setAssertive : setPolite)((entries) => keep(entries, message));
  }, []);
  return (
    <AnnounceContext.Provider value={announce}>
      {children}
      <div
        className="visually-hidden"
        role="log"
        aria-live="polite"
        aria-atomic="false"
        aria-label="Announcements"
      >
        {polite.map((entry) => (
          <p key={entry.id}>{entry.message}</p>
        ))}
      </div>
      <div
        className="visually-hidden"
        role="log"
        aria-live="assertive"
        aria-atomic="false"
        aria-label="Errors"
      >
        {assertive.map((entry) => (
          <p key={entry.id}>{entry.message}</p>
        ))}
      </div>
    </AnnounceContext.Provider>
  );
}

/** Says a message in the polite region, or in the assertive one for an error. */
export function useAnnounce(): Announce {
  const announce = useContext(AnnounceContext);
  if (!announce) throw new Error("useAnnounce needs an AnnouncerProvider (the frame mounts one)");
  return announce;
}
