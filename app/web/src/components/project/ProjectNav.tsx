/**
 * The top of each of a project's pages: where the project sits (Projects › its name), then its
 * pages as tabs (its documents, its journey map and its conversations), the one shown marked as
 * current. The same block on each page, so moving between a project's documents and its journey
 * map is one press from either, and nothing moves when the page changes.
 *
 * Its conversations open on the conversation page, in this project: a project's page makes the
 * project the one the app is working in when it reads it (docs/specs/app.md).
 */

import "./ProjectNav.css";

import { FileText, Map as MapIcon, MessagesSquare, type LucideIcon } from "lucide-react";

import { Link, journeyPath } from "../../route";

export type ProjectTab = "documents" | "journey";

export function projectPath(projectId: string): string {
  return `/projects/${encodeURIComponent(projectId)}`;
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
  const tabs: { id: ProjectTab | "conversations"; to: string; label: string; icon: LucideIcon }[] = [
    { id: "documents", to: projectPath(projectId), label: "Documents", icon: FileText },
    { id: "journey", to: journeyPath(projectId), label: "Journey map", icon: MapIcon },
    { id: "conversations", to: "/", label: "Conversations", icon: MessagesSquare },
  ];
  return (
    <div className="project-nav">
      <nav aria-label="Breadcrumb" className="project-breadcrumb">
        <ol>
          <li>
            <Link to="/projects">Projects</Link>
          </li>
          <li>{name ?? "This project"}</li>
        </ol>
      </nav>
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
