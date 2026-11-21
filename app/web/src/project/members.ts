/**
 * A project's members, as the server gives them (`/api/projects/{id}/members`, #391): who they
 * are, their roles, and what the person asking may do. The members page offers only what the
 * answer says the person may do; the server checks every change again.
 */

import { createContext, useContext } from "react";

import type { ProjectMember, ProjectMembers } from "../api/generated/responses";
import { json } from "../http";
import type { Problem } from "../run/types";

export type { ProjectMember, ProjectMembers } from "../api/generated/responses";
export type MemberRole = ProjectMember["role"];

/** A change of members the server refused, with its Problem Details: the last owner, someone
 * already a member or not one, or a request it may not make. */
export class MembersRefused extends Error {
  constructor(readonly problem: Problem) {
    super(problem.detail ?? problem.title);
    this.name = "MembersRefused";
  }
}

export interface MembersApi {
  members(projectId: string, signal?: AbortSignal): Promise<ProjectMembers>;
  /** Add the person `member` names, by ORCID iD or the identifier they sign in with. */
  addMember(projectId: string, member: string, role: MemberRole): Promise<ProjectMembers>;
  changeRole(projectId: string, memberId: string, role: MemberRole): Promise<ProjectMembers>;
  /** Remove a member, or leave by naming oneself; null once the person has left, when the
   * project is no longer theirs to read. */
  removeMember(projectId: string, memberId: string): Promise<ProjectMembers | null>;
}

function membersPath(projectId: string): string {
  return `/api/projects/${encodeURIComponent(projectId)}/members`;
}

function parse<T>(response: Response): Promise<T> {
  return json<T>(response, (status, problem) =>
    problem && status >= 400 && status !== 401 ? new MembersRefused(problem) : null,
  );
}

function sending(method: string, body?: unknown): RequestInit {
  return {
    method,
    headers: { "content-type": "application/json" },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  };
}

export const httpMembersApi: MembersApi = {
  async members(projectId, signal) {
    return parse(await fetch(membersPath(projectId), signal ? { signal } : {}));
  },
  async addMember(projectId, member, role) {
    return parse(await fetch(membersPath(projectId), sending("POST", { member, role })));
  },
  async changeRole(projectId, memberId, role) {
    return parse(
      await fetch(membersPath(projectId), sending("PATCH", { member_id: memberId, role })),
    );
  },
  async removeMember(projectId, memberId) {
    const query = new URLSearchParams({ member_id: memberId });
    const response = await fetch(`${membersPath(projectId)}?${query}`, sending("DELETE"));
    if (response.status === 204) return null;
    return parse(response);
  },
};

export const MembersApiContext = createContext<MembersApi>(httpMembersApi);

export function useMembersApi(): MembersApi {
  return useContext(MembersApiContext);
}
