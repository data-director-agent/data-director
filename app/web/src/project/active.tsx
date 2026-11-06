/**
 * The project the shell is working in (docs/specs/app.md). The app works in one project at a
 * time: the conversation page lists that project's conversations, starts a new one in it, and
 * describes it beside the conversation. With none active, the first message starts a new project,
 * which becomes the active one.
 *
 * Which project is active is a convenience of this browser, kept in `localStorage` as the theme
 * is, so it may come back empty; the server decides what the person may read, and a remembered
 * project the server no longer lists is dropped.
 */

import {
  type ReactNode,
  createContext,
  createElement,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

import { type ProjectSummary, useProjectApi } from "./api";

const KEY = "dd-project";

export interface ActiveProject {
  /** The active project, or null when the next message is to start a new one. */
  projectId: string | null;
  /** The projects the person may switch to, most recently active first. */
  projects: ProjectSummary[];
  setProjectId(projectId: string | null): void;
  /** Reads the projects again, as after a message has started or changed one. */
  reloadProjects(): void;
}

function remembered(): string | null {
  try {
    return localStorage.getItem(KEY);
  } catch {
    return null;
  }
}

function remember(projectId: string | null): void {
  try {
    if (projectId === null) localStorage.removeItem(KEY);
    else localStorage.setItem(KEY, projectId);
  } catch {
    // Storage may be blocked; the project is still active until the page is reloaded.
  }
}

/** Without a provider no project is active and nothing is remembered, as where the app keeps no
 * projects. */
const ActiveProjectContext = createContext<ActiveProject>({
  projectId: null,
  projects: [],
  setProjectId: () => undefined,
  reloadProjects: () => undefined,
});

export function ActiveProjectProvider({ children }: { children: ReactNode }) {
  const api = useProjectApi();
  const [projectId, setActive] = useState<string | null>(remembered);
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [checked, setChecked] = useState(false);
  const [generation, setGeneration] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    api.projects(controller.signal).then(
      (listed) => {
        setProjects(listed);
        setChecked(true);
      },
      () => undefined,
    );
    return () => controller.abort();
  }, [api, generation]);

  // Once, on the first list read: a remembered project the server no longer lists is forgotten.
  // Later reads keep the active project even if it is not listed yet, as one just started is not.
  const [validated, setValidated] = useState(false);
  useEffect(() => {
    if (!checked || validated) return;
    setValidated(true);
    if (projectId !== null && !projects.some((p) => p.project_id === projectId)) {
      setActive(null);
      remember(null);
    }
  }, [checked, validated, projectId, projects]);

  const setProjectId = useCallback((next: string | null) => {
    setActive(next);
    remember(next);
  }, []);
  const reloadProjects = useCallback(() => setGeneration((n) => n + 1), []);

  const value = useMemo(
    () => ({ projectId, projects, setProjectId, reloadProjects }),
    [projectId, projects, setProjectId, reloadProjects],
  );
  return createElement(ActiveProjectContext.Provider, { value }, children);
}

export function useActiveProject(): ActiveProject {
  return useContext(ActiveProjectContext);
}

/** A test's stand-in for the provider, holding `value` as it is. */
export const ActiveProjectTestContext = ActiveProjectContext;
