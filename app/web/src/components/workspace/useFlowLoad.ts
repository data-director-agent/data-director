/** The Blueprint's phases and steps, read once; if they fail, only the phase tracker says so. */

import { useFlowApi } from "../../flow/api";
import { useResource } from "../../useResource";
import type { FlowLoad } from "./PhaseTracker";

export function useFlowLoad(): FlowLoad {
  const flowApi = useFlowApi();
  const read = useResource("flow", (_, signal) => flowApi.get(signal)).resource;
  return read.state === "loaded" ? { state: "loaded", flow: read.value } : read;
}
