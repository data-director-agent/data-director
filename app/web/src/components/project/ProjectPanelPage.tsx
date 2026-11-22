/**
 * One of a project's tabs that is not its documents or its journey map (docs/specs/app.md): the
 * project's people, its facts, the repository chosen, the FAIR feedback on its metadata record,
 * the statement of how generative AI was used, or the deposit package, at `/projects/{id}/{tab}`.
 * Each is the panel that shows it, under the project's breadcrumb and tabs; the panel reads what
 * it shows itself.
 *
 * A project the person may read becomes the one the app is working in, as on its other pages.
 */

import { useEffect } from "react";

import { useActiveProject } from "../../project/active";
import { projectName } from "../../project/name";
import type { ProjectTab } from "../../route";
import { PageHeader } from "../frame/PageHeader";
import { DepositPanel } from "./DepositPanel";
import { FairnessPanel } from "../fairness/FairnessPanel";
import { DisclosurePanel } from "./DisclosurePanel";
import { FactsPanel } from "./FactsPanel";
import { PeoplePanel } from "./PeoplePanel";
import { ProjectNav, tabLabel } from "./ProjectNav";
import { RepositoryPanel } from "./RepositoryPanel";

export type PanelTab = Exclude<ProjectTab, "documents" | "journey">;

function Panel({ projectId, tab }: { projectId: string; tab: PanelTab }) {
  switch (tab) {
    case "people":
      return <PeoplePanel projectId={projectId} />;
    case "facts":
      return <FactsPanel projectId={projectId} revision={0} />;
    case "repository":
      return <RepositoryPanel projectId={projectId} revision={0} />;
    case "fair":
      return <FairnessPanel projectId={projectId} />;
    case "ai-use":
      return <DisclosurePanel projectId={projectId} revision={0} />;
    case "deposit":
      return <DepositPanel projectId={projectId} revision={0} />;
  }
}

export function ProjectPanelPage({ projectId, tab }: { projectId: string; tab: PanelTab }) {
  const { projects, setProjectId } = useActiveProject();
  const project = projects.find((p) => p.project_id === projectId) ?? null;
  const listed = project !== null;
  const name = project ? projectName(project) : null;

  useEffect(() => {
    if (listed) setProjectId(projectId);
  }, [listed, projectId, setProjectId]);

  return (
    <>
      <ProjectNav projectId={projectId} name={name} current={tab} />
      <PageHeader title={`${name ?? "This project"}: ${tabLabel(tab)}`} titleHidden />
      <Panel projectId={projectId} tab={tab} />
    </>
  );
}
