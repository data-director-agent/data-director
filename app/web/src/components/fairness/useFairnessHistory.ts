/**
 * The FAIR reports stored in a project, newest first, read again whenever `refresh` changes (a
 * turn has settled), so that feedback asked for in the conversation shows as soon as it lands.
 */

import {
  type Assessment,
  FAIRNESS_CLASS,
  assessments,
} from "../../project/fairness";
import { useProjectRunsApi } from "../../project/projectRuns";
import type { Envelope } from "../../run/types";
import { type Resource, useResource } from "../../useResource";

export function useFairnessHistory(
  projectId: string | null,
  refresh?: unknown,
): Resource<Assessment[]> {
  const api = useProjectRunsApi();
  const { resource } = useResource(
    projectId,
    async (id, signal) =>
      assessments(
        (await api.runs(id, FAIRNESS_CLASS, signal)).runs as Envelope[],
      ),
    refresh,
  );
  return resource;
}
