/**
 * The process-flow endpoint, behind one interface so tests can stand in for the server.
 */

import { createContext, useContext } from "react";

import type { ProcessFlow } from "./types";

export interface FlowApi {
  get(signal?: AbortSignal): Promise<ProcessFlow>;
}

export const httpFlowApi: FlowApi = {
  async get(signal) {
    const response = await fetch("/api/process-flow", signal ? { signal } : {});
    if (!response.ok) throw new Error(`the server answered ${response.status}`);
    return (await response.json()) as ProcessFlow;
  },
};

export const FlowApiContext = createContext<FlowApi>(httpFlowApi);

export function useFlowApi(): FlowApi {
  return useContext(FlowApiContext);
}
