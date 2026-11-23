/**
 * The project open on a project page, as the server says the reader may see it
 * (`GET /api/projects/{id}`): whether they are in it as a member or as its data steward, and what
 * the harness lets them do there (docs/specs/stewardship.md, "Boundaries"). Every page of a project
 * reads it once, here, so that each part renders the same answer and decides nothing itself.
 *
 * Until the read lands, or if it fails, there is no view: the parts show what a member sees, and
 * the server still checks every request.
 */

import { createContext, type ReactNode, useCallback, useContext, useMemo } from "react";

import { useResource } from "../useResource";
import { type ProjectView, permits, useStewardApi } from "./steward";

interface Held {
  view: ProjectView | null;
  /** Reads the view again, as after a steward's step changes what they may do. */
  reload(): void;
}

const ProjectViewContext = createContext<Held>({ view: null, reload: () => undefined });

export function ProjectViewProvider({ projectId, children }: { projectId: string; children: ReactNode }) {
  const api = useStewardApi();
  const read = useResource(projectId, (id, signal) => api.view(id, signal));
  const { reload } = read;
  const again = useCallback(() => reload(), [reload]);
  const value = useMemo(() => ({ view: read.latest ?? null, reload: again }), [read.latest, again]);
  return <ProjectViewContext.Provider value={value}>{children}</ProjectViewContext.Provider>;
}

/** The project open, as the reader may see it; null while it is not known. */
export function useProjectView(): Held {
  return useContext(ProjectViewContext);
}

/** `children`, where the harness lets the reader take `action` in the project open; nothing where
 * it does not, as for a data steward reading a researcher's project. */
export function Permitted({ action, children }: { action: string; children: ReactNode }) {
  const { view } = useProjectView();
  return permits(view, action) ? children : null;
}
