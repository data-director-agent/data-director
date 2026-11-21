/** Who is signed in, for a page that shows whose work is whose (#391). */

import { useEffect, useState } from "react";

import { useSessionApi } from "./api";

/** The signed-in person's principal identifier, or null while it is not known or nobody is. */
export function useViewerId(): string | null {
  const sessions = useSessionApi();
  const [viewer, setViewer] = useState<string | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    sessions.get(controller.signal).then(
      (session) => setViewer(session.principal?.principalId ?? null),
      () => undefined,
    );
    return () => controller.abort();
  }, [sessions]);
  return viewer;
}
