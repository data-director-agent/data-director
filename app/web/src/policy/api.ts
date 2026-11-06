/**
 * The deployment's policy, as the policy gate holds every run to it (`GET /api/policy`,
 * docs/specs/app.md), behind one interface so tests can stand in for the server. The shell draws
 * it and decides nothing from it.
 */

import { createContext, useContext } from "react";

import { checkSignedIn } from "../session/api";

export interface PolicyAgent {
  agent_id: string;
  /** The action class the profile assigns the agent. */
  action_class: string;
  requires_approval: boolean;
}

export interface Policy {
  profile: {
    id: string;
    version: number;
    /** What every stored run records as the rules it was held to. */
    ref: string;
    /** SHA-256 of the profile file's bytes. */
    digest: string;
    /** Empty: the profile says nothing about itself. */
    description: string;
    /** The agent a conversation goes to; null when the profile names none. */
    orchestrator: string | null;
  };
  agents: PolicyAgent[];
  actions_requiring_approval: string[];
}

export interface PolicyApi {
  get(signal?: AbortSignal): Promise<Policy>;
}

export const httpPolicyApi: PolicyApi = {
  async get(signal) {
    const response = await fetch("/api/policy", signal ? { signal } : {});
    checkSignedIn(response);
    if (!response.ok) throw new Error(`the server answered ${response.status}`);
    return (await response.json()) as Policy;
  },
};

export const PolicyApiContext = createContext<PolicyApi>(httpPolicyApi);

export function usePolicyApi(): PolicyApi {
  return useContext(PolicyApiContext);
}
