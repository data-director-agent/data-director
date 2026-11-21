/**
 * Which project the workspace is in, and a way to switch (docs/specs/app.md). The app works in one
 * project at a time; choosing another opens its conversations, and **New project** opens a dialog
 * that creates one (rule 27), so that Data Director can ask its intake questions before anything
 * is typed. **New project** is also a button beside the switcher, so that starting one does not
 * depend on opening the list. A project is named as the projects page names it. While one is active, **Project details** beside the switcher opens its page
 * (`/projects/{project_id}`), so a person can get from the conversation to its documents.
 */

import "./ProjectSwitcher.css";

import { ChevronDown, FolderOpen, FolderPlus } from "lucide-react";
import { useState } from "react";
import {
  Button as AriaButton,
  Label,
  ListBox,
  ListBoxItem,
  Popover,
  Select,
  SelectValue,
} from "react-aria-components";

import { useActiveProject } from "../../project/active";
import { projectName } from "../../project/name";
import { Link } from "../../route";
import { Button } from "../ui/Button";
import { NewProjectDialog } from "./NewProjectDialog";

/** The key of the New project choice; no project identifier (a UUIDv7) can be it. */
const NEW = "new-project";

export function ProjectSwitcher() {
  const { projectId, projects, setProjectId } = useActiveProject();
  // One started a moment ago is not listed until it holds something (docs/specs/app.md).
  const unlisted = projectId !== null && !projects.some((p) => p.project_id === projectId);
  const [creating, setCreating] = useState(false);
  return (
    <div className="project-switcher-group">
      <Select
        className="project-switcher"
        // With none active, as before a first message started one, no project is chosen, so that
        // New project can still be chosen.
        selectedKey={projectId}
        placeholder="No project"
        onSelectionChange={(key) => {
          if (key === NEW) setCreating(true);
          else if (key !== null) setProjectId(String(key));
        }}
      >
        <Label className="project-switcher-label">Project</Label>
        <AriaButton className="button button-secondary project-switcher-button">
          <SelectValue className="project-switcher-value" />
          <ChevronDown className="button-icon" size="1.125em" aria-hidden="true" />
        </AriaButton>
        <Popover className="project-switcher-popover">
          <ListBox className="project-switcher-list">
            {projects.map((project) => {
              const name = projectName(project);
              return (
                <ListBoxItem
                  key={project.project_id}
                  id={project.project_id}
                  textValue={name}
                  className="project-switcher-option"
                >
                  {name}
                </ListBoxItem>
              );
            })}
            {unlisted && (
              <ListBoxItem
                id={projectId}
                textValue="Untitled project"
                className="project-switcher-option"
              >
                Untitled project
              </ListBoxItem>
            )}
            <ListBoxItem id={NEW} textValue="New project" className="project-switcher-option">
              <FolderPlus className="button-icon" size="1.125em" aria-hidden="true" /> New project
            </ListBoxItem>
          </ListBox>
        </Popover>
      </Select>
      <Button icon={FolderPlus} variant="secondary" onPress={() => setCreating(true)}>
        New project
      </Button>
      {projectId !== null && (
        <Link to={`/projects/${encodeURIComponent(projectId)}`} className="button button-secondary">
          <FolderOpen className="button-icon" size="1.125em" aria-hidden="true" />
          Project details
        </Link>
      )}
      <NewProjectDialog isOpen={creating} onOpenChange={setCreating} />
    </div>
  );
}
