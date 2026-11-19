/**
 * The deployment's policy, as the policy gate holds every run to it (`GET /api/policy`,
 * docs/specs/app.md), behind one interface so tests can stand in for the server. The shell draws
 * it and decides nothing from it.
 */

import { createContext, useContext } from "react";

import type { Policy } from "../api/generated/responses";
import { checkSignedIn } from "../session/api";

export type { Policy, PolicyAgent } from "../api/generated/responses";

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
