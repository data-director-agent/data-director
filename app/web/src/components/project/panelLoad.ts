/** How a project's panel reads what it shows: loading, failed with a message, or loaded. */

export type PanelLoad<T> =
  | { state: "loading" }
  | { state: "failed"; message: string }
  | { state: "loaded"; value: T };

/** An error's message, for a panel to show. */
export function message(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

/**
 * Read with `read` into `set`, as a panel's effect does when it opens; returns the effect's
 * cleanup, which abandons the read so a panel that has gone shows nothing of it.
 */
export function loadInto<T>(
  read: (signal: AbortSignal) => Promise<T>,
  set: (load: PanelLoad<T>) => void,
): () => void {
  const controller = new AbortController();
  read(controller.signal).then(
    (value) => set({ state: "loaded", value }),
    (error: unknown) => {
      if (!controller.signal.aborted) set({ state: "failed", message: message(error) });
    },
  );
  return () => controller.abort();
}
