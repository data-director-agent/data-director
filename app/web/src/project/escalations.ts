/**
 * A project's escalations to a data steward, and what stewards did in it, as the server gives them
 * (`/api/projects/{id}/escalations` and `/api/projects/{id}/stewarding`, #373, #374). A member
 * opens an escalation they confirmed, and replies to, withdraws or re-opens one
 * (docs/specs/stewardship.md, invariants 4, 5 and 11). The server decides where it goes and which
 * moves are allowed; the shell renders what it answers.
 */

import { createContext, useContext } from "react";

import type {
  Escalation,
  EscalationState,
  OriginKind,
  ProjectEscalations,
  ProjectStewarding,
} from "../api/generated/responses";
import { json } from "../http";
import type { Problem } from "../run/types";

export type {
  Escalation,
  EscalationState,
  OriginKind,
  ProjectEscalations,
  ProjectStewarding,
  StewardMessage,
} from "../api/generated/responses";

/** Where a new escalation comes from: the researcher, or a run of the project. */
export interface NewOrigin {
  kind: OriginKind;
  /** The run it comes from; absent for one the researcher raised. */
  invocation_id?: string;
}

export interface NewEscalation {
  note: string;
  origin: NewOrigin;
  /** The lines the researcher was shown of what is shared, as they confirmed them. */
  scope_shared: string[];
  /** The team picked, where the project has none and the deployment several. */
  team_id?: string;
}

/** The moves the researcher's side may make. */
export type ResearcherMove = "reply" | "withdraw" | "reopen";

/** The states in which an escalation is still with the stewards. */
export const LIVE_STATES: readonly EscalationState[] = ["open", "taken", "waiting_for_researcher"];

/** At most this many characters in a note, as the harness allows (`NOTE_MAX_LENGTH`). */
export const NOTE_MAX_LENGTH = 4000;
/** At most this many lines of what is shared, each at most `SCOPE_LINE_MAX_LENGTH` characters. */
export const SCOPE_MAX_LINES = 20;
export const SCOPE_LINE_MAX_LENGTH = 500;

/** An escalation or a move the server refused, with its Problem Details; `slug` names why. */
export class EscalationRefused extends Error {
  readonly slug: string;
  constructor(readonly problem: Problem) {
    super(problem.detail ?? problem.title);
    this.name = "EscalationRefused";
    this.slug = problem.type.split("/").pop() ?? "";
  }
}

export interface EscalationsApi {
  escalations(projectId: string, signal?: AbortSignal): Promise<ProjectEscalations>;
  open(projectId: string, escalation: NewEscalation): Promise<ProjectEscalations>;
  move(projectId: string, escalationId: string, move: ResearcherMove, note?: string): Promise<Escalation>;
  stewarding(projectId: string, signal?: AbortSignal): Promise<ProjectStewarding>;
}

function projectPath(projectId: string): string {
  return `/api/projects/${encodeURIComponent(projectId)}`;
}

function parse<T>(response: Response): Promise<T> {
  return json<T>(response, (status, problem) =>
    problem && status === 409 ? new EscalationRefused(problem) : null,
  );
}

function posting(body: unknown): RequestInit {
  return { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) };
}

export const httpEscalationsApi: EscalationsApi = {
  async escalations(projectId, signal) {
    return parse(await fetch(`${projectPath(projectId)}/escalations`, signal ? { signal } : {}));
  },
  async open(projectId, escalation) {
    return parse(await fetch(`${projectPath(projectId)}/escalations`, posting(escalation)));
  },
  async move(projectId, escalationId, move, note) {
    const path = `${projectPath(projectId)}/escalations/${encodeURIComponent(escalationId)}`;
    return parse(await fetch(path, posting(note === undefined ? { move } : { move, note })));
  },
  async stewarding(projectId, signal) {
    return parse(await fetch(`${projectPath(projectId)}/stewarding`, signal ? { signal } : {}));
  },
};

export const EscalationsApiContext = createContext<EscalationsApi>(httpEscalationsApi);

export function useEscalationsApi(): EscalationsApi {
  return useContext(EscalationsApiContext);
}

/** The live escalation that came from the run `invocationId`, if there is one. */
export function liveFor(escalations: readonly Escalation[], invocationId: string): Escalation | undefined {
  return escalations.find(
    (e) => e.origin.invocation_id === invocationId && LIVE_STATES.includes(e.state),
  );
}
