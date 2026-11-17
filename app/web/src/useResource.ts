/**
 * One way to read something from the server for a component: the read is keyed (by project, say),
 * aborted when the key changes, when it is read again or when the component goes, and a read of
 * another key is never shown as this one's. Read again when `refresh` changes, or on `reload`.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { errorMessage } from "./run/api";

export type Resource<T> =
  | { state: "loading" }
  | { state: "loaded"; value: T }
  | { state: "failed"; message: string };

/** What to do as each read lands, beside keeping its result. */
export interface ResourceEvents<T> {
  loaded?(value: T, key: string): void;
  failed?(message: string, key: string): void;
}

export interface ResourceRead<T> {
  /** The latest read of the current key; `loading` until one lands, or while there is no key. */
  resource: Resource<T>;
  /** The latest value read of the current key, kept when a later read of it fails. */
  latest: T | undefined;
  /**
   * Holds `value` as read for `key`, as when a change the page made returns the new value; a value
   * for a key other than the current one, as after a switch of project, is dropped.
   */
  set(key: string, value: T): void;
  /** Reads the current key again. */
  reload(): void;
}

interface Held<T> {
  key: string;
  resource: Resource<T>;
  latest: T | undefined;
}

const LOADING = { state: "loading" } as const;

export function useResource<T>(
  key: string | null,
  load: (key: string, signal: AbortSignal) => Promise<T>,
  refresh?: unknown,
  events?: ResourceEvents<T>,
): ResourceRead<T> {
  const [held, setHeld] = useState<Held<T> | null>(null);
  const [tick, setTick] = useState(0);
  // The latest callbacks, so that callers need not keep them stable.
  const latestLoad = useRef(load);
  const latestEvents = useRef(events);
  const currentKey = useRef(key);
  useEffect(() => {
    latestLoad.current = load;
    latestEvents.current = events;
    currentKey.current = key;
  });

  useEffect(() => {
    if (key === null) return;
    const abort = new AbortController();
    latestLoad.current(key, abort.signal).then(
      (value) => {
        if (abort.signal.aborted) return;
        setHeld({ key, resource: { state: "loaded", value }, latest: value });
        latestEvents.current?.loaded?.(value, key);
      },
      (e: unknown) => {
        if (abort.signal.aborted) return;
        const message = errorMessage(e);
        setHeld((was) => ({
          key,
          resource: { state: "failed", message },
          latest: was?.key === key ? was.latest : undefined,
        }));
        latestEvents.current?.failed?.(message, key);
      },
    );
    return () => abort.abort();
  }, [key, refresh, tick]);

  const set = useCallback((of: string, value: T) => {
    if (of !== currentKey.current) return;
    setHeld({ key: of, resource: { state: "loaded", value }, latest: value });
  }, []);
  const reload = useCallback(() => setTick((t) => t + 1), []);

  const current = key !== null && held?.key === key ? held : null;
  return { resource: current?.resource ?? LOADING, latest: current?.latest, set, reload };
}
