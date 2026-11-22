/**
 * The open conversation, kept above the pages so that it outlives the Conversation page: someone
 * who leaves it while a reply is awaited, for the Activity log or a project, finds the
 * conversation, the message sent and its run still streaming when they come back, and a reply that
 * arrived meanwhile in its place (docs/specs/app.md, "The open conversation").
 *
 * The page's hooks keep their state here, under a name, rather than in the component
 * (`useSessionState`, `useSessionRef`). A turn sent before the page was left goes on writing to
 * the session, so what it brings back is there for the page drawn next. The session is held in
 * memory for this tab and the person signed in: a reload, or the server cancelling a run whose
 * stream closed, starts it empty, as the address then reopens the conversation from what the
 * server stored.
 *
 * Outside a provider each component keeps its own session, so a hook can be drawn on its own in a
 * test, and loses it when it goes, as before.
 */

import {
  createContext,
  type ReactNode,
  type SetStateAction,
  useCallback,
  useContext,
  useMemo,
  useState,
  useSyncExternalStore,
} from "react";

/** Values by name, and who to tell when one changes. */
class SessionStore {
  private readonly values = new Map<string, unknown>();
  private readonly listeners = new Set<() => void>();

  has(name: string): boolean {
    return this.values.has(name);
  }

  get(name: string): unknown {
    return this.values.get(name);
  }

  /** Holds `value` without telling anyone: for what is not drawn, as a ref is not. */
  hold(name: string, value: unknown): void {
    this.values.set(name, value);
  }

  set(name: string, value: unknown): void {
    if (this.values.has(name) && Object.is(this.values.get(name), value)) return;
    this.values.set(name, value);
    for (const listener of this.listeners) listener();
  }

  readonly subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };
}

const SessionContext = createContext<SessionStore | null>(null);

export function ConversationSessionProvider({ children }: { children: ReactNode }) {
  const [store] = useState(() => new SessionStore());
  return <SessionContext.Provider value={store}>{children}</SessionContext.Provider>;
}

/** The provider's session, or one of the component's own outside a provider. */
function useStore(): SessionStore {
  const [own] = useState(() => new SessionStore());
  return useContext(SessionContext) ?? own;
}

/**
 * `useState` kept in the session under `name`. `initial` is what it holds until first set, so it
 * must be the same value each time (a primitive or a constant). The setter keeps working after the
 * component has gone, and the component drawn next sees what it set.
 */
export function useSessionState<T>(
  name: string,
  initial: T,
): [T, (next: SetStateAction<T>) => void] {
  const store = useStore();
  const read = () => (store.has(name) ? (store.get(name) as T) : initial);
  const value = useSyncExternalStore(store.subscribe, read, read);
  const set = useCallback(
    (next: SetStateAction<T>) => {
      const held = store.has(name) ? (store.get(name) as T) : initial;
      store.set(name, typeof next === "function" ? (next as (held: T) => T)(held) : next);
    },
    // `initial` is the same value each time.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [store, name],
  );
  return [value, set];
}

/** A ref kept in the session under `name`: setting it draws nothing. */
export function useSessionRef<T>(name: string, initial: T): { current: T } {
  const store = useStore();
  return useMemo(
    () => ({
      get current(): T {
        return store.has(name) ? (store.get(name) as T) : initial;
      },
      set current(value: T) {
        store.hold(name, value);
      },
    }),
    // `initial` is the same value each time.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [store, name],
  );
}
