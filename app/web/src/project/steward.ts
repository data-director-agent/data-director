/**
 * What a data steward reads and does across projects (docs/specs/stewardship.md, invariants 3, 4
 * and 6; #376): the escalations routed to their teams (`GET /api/steward/escalations`), the moves
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
  ProjectView,
  QueuedEscalation,
  StewardQueue,
} from "../api/generated/responses";
import { json } from "../http";
import { EscalationRefused } from "./escalations";

export type { PermittedMove, ProjectView, QueuedEscalation } from "../api/generated/responses";

/** A move on an escalation, on either side. */
export type MoveName = PermittedMove["move"];

/** The steps a steward takes in a project that carry a note. */
export type StewardStep = "messages" | "pause" | "resume";

export interface StewardApi {
  /** The escalations routed to the signed-in person's teams; by default the live ones. */
  queue(states: readonly EscalationState[], signal?: AbortSignal): Promise<QueuedEscalation[]>;
  move(projectId: string, escalationId: string, move: MoveName, note?: string): Promise<Escalation>;
  /** The project as the person may see it, with whether they act in it as a member or a steward. */
  view(projectId: string, signal?: AbortSignal): Promise<ProjectView>;
  /** A message to the researchers, or a pause or its lifting, with its note. */
  step(projectId: string, step: StewardStep, note: string): Promise<void>;
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
  async move(projectId, escalationId, move, note) {
    const path = `/api/steward/escalations/${encodeURIComponent(projectId)}/${encodeURIComponent(escalationId)}`;
    return parse(await fetch(path, posting(note === undefined ? { move } : { move, note })));
  },
  async view(projectId, signal) {
    return parse(await fetch(projectPath(projectId), signal ? { signal } : {}));
  },
  async step(projectId, step, note) {
    await parse(await fetch(`${projectPath(projectId)}/steward/${step}`, posting({ note })));
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

/** Whether `view` is a project the reader opened as its data steward. */
export function asSteward(view: ProjectView | null | undefined): boolean {
  return view?.permitted_actions.acting_as === "steward";
}

/** The moves of `escalation` the harness lets the reader make. */
export function movesPermitted(escalation: Escalation): MoveName[] {
  return escalation.permitted_moves.filter((m) => m.permitted).map((m) => m.move);
}
