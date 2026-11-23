/** A fake of what a data steward reads and does, for components' own tests. */

import { type Mock, vi } from "vitest";

import projectsFixture from "../../fixtures/steward-projects.json";
import queueFixture from "../../fixtures/steward-queue.json";
import viewFixture from "../../fixtures/project-steward-view.json";
import type { ProjectView, QueuedEscalation, StewardApi, StewardProject } from "../project/steward";
import { NO_STEWARDING } from "./escalations";

export const QUEUE = queueFixture.escalations as QueuedEscalation[];

function firstOf(queue: QueuedEscalation[]): QueuedEscalation {
  const [row] = queue;
  if (!row) throw new Error("no escalation in the fixture");
  return row;
}

/** The fixture's one request, routed to the steward's team. */
export const ROW = firstOf(QUEUE);

/** The projects the steward may see: the one with the fixture's request. */
export const PROJECTS = projectsFixture as StewardProject[];

/** A project as its steward opens it, with what the harness lets them do there. */
export const VIEW = viewFixture as ProjectView;

/** `VIEW` as one of the project's members sees it. */
export const MEMBER_VIEW: ProjectView = { ...VIEW, permitted_actions: { acting_as: "member", actions: [] } };

export function fakeStewardApi(
  view: ProjectView = VIEW,
  queue: QueuedEscalation[] = QUEUE,
  projects: StewardProject[] = PROJECTS,
) {
  return {
    queue: vi.fn<StewardApi["queue"]>(() => Promise.resolve(queue)),
    projects: vi.fn<StewardApi["projects"]>(() => Promise.resolve({ items: projects, next: null })),
    move: vi.fn<StewardApi["move"]>(() => Promise.resolve({ ...ROW, state: "taken" })),
    view: vi.fn<StewardApi["view"]>(() => Promise.resolve(view)),
    step: vi.fn<StewardApi["step"]>(() => Promise.resolve()),
    decideGate: vi.fn<StewardApi["decideGate"]>(() => Promise.resolve(NO_STEWARDING)),
    proposeEdit: vi.fn<StewardApi["proposeEdit"]>((_, documentId, edit) =>
      Promise.resolve({ document_id: documentId, version: edit.version + 1 }),
    ),
  } satisfies Record<keyof StewardApi, Mock>;
}
