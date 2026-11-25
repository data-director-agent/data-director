/**
 * What a data steward reads and does across projects (docs/specs/stewardship.md, invariants 3, 4
 * and 6; #376): the escalations routed to their teams (`GET /api/steward/escalations`), the
 * projects they may see (`GET /api/steward/projects`, #232), each listing a recorded read, the moves
 * they make on one (`POST /api/steward/escalations/{project_id}/{escalation_id}`), a project as
 * they may see it, with what they may do in it (`GET /api/projects/{id}`), and the steps they take
 * there (`POST /api/projects/{id}/steward/…`). The harness decides each; the shell renders what it
 * answers, and holds no policy of its own.
 */

import { createContext, useContext } from "react";

import type {
  Escalation,
  EscalationState,
  PermittedMove,
  ProjectStewarding,
  ProjectView,
  ProposedVersion,
  QueuedEscalation,
  StewardProject,
  StewardQueue,
} from "../api/generated/responses";
import { json } from "../http";
import { nextCursor } from "../run/api";
import { EscalationRefused } from "./escalations";

export type {
  PermittedMove,
  ProjectView,
  ProposedVersion,
  QueuedEscalation,
  StewardProject,
} from "../api/generated/responses";

/** One page of the projects a steward may see, and the cursor of the next, null on the last. */
export interface StewardProjectsPage {
  items: StewardProject[];
  next: string | null;
}

/** A move on an escalation, on either side. */
export type MoveName = PermittedMove["move"];

/** A steward's version of a document: the version edited, the digest of its text, and the new text. */
export interface StewardEdit {
  version: number;
  digest: string;
  text: string;
}

/** The steps a steward takes in a project that carry a note. */
export type StewardStep = "messages" | "pause" | "resume";

export interface StewardApi {
  /** The escalations routed to the signed-in person's teams; by default the live ones. */
  queue(states: readonly EscalationState[], signal?: AbortSignal): Promise<QueuedEscalation[]>;
  /** Makes a move, with its note and, for `reassign` or `transfer`, the colleague's or team's id. */
  move(projectId: string, escalationId: string, move: MoveName, note?: string, to?: string): Promise<Escalation>;
  /** A page of the projects the person may see as a data steward, the one created last first;
   * the server records each one listed as read by them. */
  projects(before: string | null, signal?: AbortSignal): Promise<StewardProjectsPage>;
  /** The project as the person may see it, with whether they act in it as a member or a steward. */
  view(projectId: string, signal?: AbortSignal): Promise<ProjectView>;
  /** A message to the researchers, or a pause or its lifting, with its note. */
  step(projectId: string, step: StewardStep, note: string): Promise<void>;
  /** Clears or refuses a run the policy gate referred to a data steward, with the reason. */
  decideGate(
    projectId: string,
    invocationId: string,
    verdict: "cleared" | "refused",
    note: string,
  ): Promise<ProjectStewarding>;
  /** Proposes the steward's version of a document, which the project's owners decide on. */
  proposeEdit(projectId: string, documentId: string, edit: StewardEdit): Promise<ProposedVersion>;
}

function parse<T>(response: Response): Promise<T> {
  return json<T>(response, (status, problem) =>
    problem && (status === 409 || status === 403) ? new EscalationRefused(problem) : null,
  );
}

function posting(body: unknown): RequestInit {
  return { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) };
}

function projectPath(projectId: string): string {
  return `/api/projects/${encodeURIComponent(projectId)}`;
}

export const httpStewardApi: StewardApi = {
  async queue(states, signal) {
    const query = new URLSearchParams(states.map((state) => ["state", state]));
    const found = await parse<StewardQueue>(
      await fetch(`/api/steward/escalations?${query.toString()}`, signal ? { signal } : {}),
    );
    return found.escalations;
  },
  async move(projectId, escalationId, move, note, to) {
    const path = `/api/steward/escalations/${encodeURIComponent(projectId)}/${encodeURIComponent(escalationId)}`;
    return parse(
      await fetch(path, posting({ move, ...(note === undefined ? {} : { note }), ...(to === undefined ? {} : { to }) })),
    );
  },
  async projects(before, signal) {
    const query = before ? `?${new URLSearchParams({ before }).toString()}` : "";
    const response = await fetch(`/api/steward/projects${query}`, signal ? { signal } : {});
    const items = await parse<StewardProject[]>(response);
    return { items, next: nextCursor(response.headers.get("Link")) };
  },
  async view(projectId, signal) {
    return parse(await fetch(projectPath(projectId), signal ? { signal } : {}));
  },
  async step(projectId, step, note) {
    await parse(await fetch(`${projectPath(projectId)}/steward/${step}`, posting({ note })));
  },
  async decideGate(projectId, invocationId, verdict, note) {
    const path = `${projectPath(projectId)}/steward/gates/${encodeURIComponent(invocationId)}`;
    return parse(await fetch(path, posting({ verdict, note })));
  },
  async proposeEdit(projectId, documentId, edit) {
    const path = `${projectPath(projectId)}/steward/documents/${encodeURIComponent(documentId)}/versions`;
    return parse(await fetch(path, posting(edit)));
  },
};

export const StewardApiContext = createContext<StewardApi>(httpStewardApi);

export function useStewardApi(): StewardApi {
  return useContext(StewardApiContext);
}

/** Whether the harness lets the reader take `action` in the project `view` shows; true while the
 * view is not known, as the server checks each request whatever the shell shows. */
export function permits(view: ProjectView | null | undefined, action: string): boolean {
  if (!view) return true;
  return view.permitted_actions.actions.some((a) => a.action === action && a.permitted);
}

/** Whether the reader opened the project as its data steward and the harness lets them take the
 * steward's `action` there; false while the view is not known, so that a member is never offered
 * a steward's control. */
export function stewardMay(view: ProjectView | null | undefined, action: string): boolean {
  return asSteward(view) && permits(view, action);
}

/** Whether `view` is a project the reader opened as its data steward. */
export function asSteward(view: ProjectView | null | undefined): boolean {
  return view?.permitted_actions.acting_as === "steward";
}

/** The moves of `escalation` the harness lets the reader make. */
export function movesPermitted(escalation: Escalation): MoveName[] {
  return escalation.permitted_moves.filter((m) => m.permitted).map((m) => m.move);
}
