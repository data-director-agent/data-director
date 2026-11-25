/**
 * The controls at the top of a project's documents page that the harness lets a member use:
 * renaming and deleting the project (an owner's), adding an inventory and attaching a document.
 * A data steward who opens the project sees none of them (docs/specs/stewardship.md, invariant 2),
 * and the project's name from the view, since it is not in their own list of projects.
 *
 * The inventory the project holds is shown to everyone who can read the project, as a chip that
 * opens it in readable form (#472); a steward, who cannot add one, can still read it.
 */

import { useMemo } from "react";

import type { DocumentationSummary } from "../../conversation/documentation";
import type { InventorySource } from "../../conversation/inventory";
import type { Directory } from "../../manifest/normalise";
import { type ProjectSummary, useProjectApi } from "../../project/api";
import { deletionName, projectName } from "../../project/name";
import { permits } from "../../project/steward";
import { useProjectView } from "../../project/view";
import { InventoryChip } from "../conversation/InventoryChip";
import { AddInventory } from "../inventory/AddInventory";
import { AttachDocumentOffer } from "./AttachDocument";
import { DeleteProject } from "./DeleteProject";
import { ProjectRename } from "./ProjectRename";

/** The project's name: as listed, or, for a steward, whose projects are not in their own list, as
 * the view names it. */
export function useProjectTitle(project: ProjectSummary | null): string | null {
  const { view } = useProjectView();
  return project ? projectName(project) : (view?.title ?? null);
}

/** The controls the harness lets a member use on the project: renaming and deleting it (an
 * owner's), adding an inventory and attaching a document. None for a data steward. */
export function MemberActions({
  projectId,
  project,
  title,
  directory,
  onRenamed,
  onInventory,
  onAttached,
}: {
  projectId: string;
  project: ProjectSummary | null;
  title: string | null;
  directory: Directory | null | undefined;
  onRenamed: () => void;
  onInventory: (saved: NonNullable<ProjectSummary["inventory"]>) => void;
  onAttached: (held: DocumentationSummary[], added: DocumentationSummary | undefined) => void;
}) {
  const { view } = useProjectView();
  const api = useProjectApi();
  const source = useMemo<InventorySource>(
    () => ({ load: (signal) => api.inventory(projectId, signal) }),
    [api, projectId],
  );
  const held = project?.inventory;
  return (
    <>
      {project && title && permits(view, "manage") && (
        <p className="project-name-actions">
          <ProjectRename
            projectId={projectId}
            name={project.title ?? title}
            named={project.title_source ?? null}
            onRenamed={onRenamed}
          />{" "}
          <DeleteProject
            projectId={projectId}
            name={title}
            typedName={deletionName(project)}
            restoreDays={project.restore_days}
          />
        </p>
      )}
      {held && (
        <p className="project-inventory">
          <InventoryChip fileCount={held.file_count} madeAt={held.inventory_made_at} source={source} />
        </p>
      )}
      {permits(view, "contribute") && (
        <>
          <p className="project-inventory-actions">
            <AddInventory projectId={projectId} replacing={held != null} onSaved={onInventory} />
          </p>
          <AttachDocumentOffer projectId={projectId} directory={directory} onAttached={onAttached} />
        </>
      )}
    </>
  );
}
