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
import { useActiveProject } from "./active";
import { type ProjectView, asSteward, permits, stewardMay, useStewardApi } from "./steward";

interface Held {
  view: ProjectView | null;
  /** Reads the view again, as after a steward's step changes what they may do. */
  reload(): void;
}

const ProjectViewContext = createContext<Held>({ view: null, reload: () => undefined });

export function ProjectViewProvider({ projectId, children }: { projectId: string | null; children: ReactNode }) {
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

/** `children`, where the reader is the project's data steward and the harness lets them take the
 * steward's `action`; nothing for a member, or while the view is not known. */
export function StewardPermitted({ action, children }: { action: string; children: ReactNode }) {
  const { view } = useProjectView();
  return stewardMay(view, action) ? children : null;
}

/** The view of the project the app is working in (`project/active`), as on the conversation page,
 * where no project is in the address. */
export function ActiveProjectViewProvider({ children }: { children: ReactNode }) {
  const { projectId } = useActiveProject();
  return <ProjectViewProvider projectId={projectId}>{children}</ProjectViewProvider>;
}

/** `projectId`, unless the reader is the project's data steward, for the parts of a page that
 * only a researcher in their own project uses, such as asking a data steward. */
export function useResearcherProject(projectId: string | null): string | null {
  const { view } = useProjectView();
  return asSteward(view) ? null : projectId;
}
