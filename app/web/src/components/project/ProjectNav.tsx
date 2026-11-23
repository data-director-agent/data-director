/**
 * The top of each of a project's pages: where the project sits (Projects › its name), then its
 * pages as tabs, in the order the work goes: what it holds (its documents, its facts, its
 * people), what is decided for the deposit (the repository chosen, the statement of how
 * generative AI was used), the check on it (the FAIR feedback on its metadata record), the
 * deposit package, then the overview and the talk (its journey map and its conversations), the
 * one shown marked as current. The same block on each
 * page, so moving between them is one press from any, and nothing moves when the page changes.
 *
 * Its conversations open on the conversation page, in this project: a project's page makes the
 * project the one the app is working in when it reads it (docs/specs/app.md).
 */

import "./ProjectNav.css";

import {
  Compass,
  FileText,
  Landmark,
  ListChecks,
  type LucideIcon,
  Map as MapIcon,
  MessagesSquare,
  Package,
  Sparkles,
  Users,
} from "lucide-react";

import { Link, type ProjectTab, projectTabPath } from "../../route";
import { StewardProvider } from "../escalation/StewardContext";
import { AskStewardControl } from "../escalation/StewardSection";

export type { ProjectTab } from "../../route";

export function projectPath(projectId: string): string {
  return projectTabPath(projectId);
}

const TABS: { id: ProjectTab; label: string; icon: LucideIcon }[] = [
  { id: "documents", label: "Documents", icon: FileText },
  { id: "facts", label: "Project facts", icon: ListChecks },
  { id: "people", label: "People", icon: Users },
  { id: "repository", label: "Repository", icon: Landmark },
  { id: "ai-use", label: "Use of generative AI", icon: Sparkles },
  { id: "fair", label: "FAIR feedback", icon: Compass },
  { id: "deposit", label: "Deposit package", icon: Package },
  { id: "journey", label: "Journey map", icon: MapIcon },
];

/** A tab's name, for a page's title. */
export function tabLabel(tab: ProjectTab): string {
  return TABS.find((t) => t.id === tab)?.label ?? tab;
}

export function ProjectNav({
  projectId,
  name,
  current,
}: {
  projectId: string;
  /** The project's name, or null while it is not known. */
  name: string | null;
  current: ProjectTab;
}) {
  const tabs = [
    ...TABS.map((t) => ({ ...t, to: projectTabPath(projectId, t.id) })),
    {
      id: "conversations",
      to: "/",
      label: "Conversations",
      icon: MessagesSquare,
    },
  ];
  return (
    <div className="project-nav">
      <div className="project-nav-top">
        <nav aria-label="Breadcrumb" className="project-breadcrumb">
          <ol>
            <li>
              <Link to="/projects">Projects</Link>
            </li>
            <li>{name ?? "This project"}</li>
          </ol>
        </nav>
        {/* Reachable on every project page (docs/ui/steward-escalation-flows.md, flow A). */}
        <StewardProvider projectId={projectId} project={{ title: name }}>
          <AskStewardControl />
        </StewardProvider>
      </div>
      <nav aria-label="Project" className="project-tabs">
        <ul>
          {tabs.map(({ id, to, label, icon: Icon }) => (
            <li key={id}>
              <Link
                to={to}
                className="project-tab"
                {...(id === current ? { "aria-current": "page" as const } : {})}
              >
                <Icon size="1em" aria-hidden="true" />
                {label}
              </Link>
            </li>
          ))}
        </ul>
      </nav>
    </div>
  );
}
