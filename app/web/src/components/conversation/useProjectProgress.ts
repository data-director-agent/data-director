/**
 * Where the project is in the flow, read with its documents: when the project is known and after
 * each turn. A read is kept with the project it is of, as the documents are, and a failed read
 * after a turn leaves the last one shown.
 */

import { useCallback, useState } from "react";

import type { ProjectProgress } from "../../flow/types";
import { useProjectApi } from "../../project/api";
import { errorMessage } from "../../run/api";
import { useResource } from "../../useResource";

export interface ProjectProgressRead {
  /** The project's progress, once read. */
  progress: ProjectProgress | undefined;
  /** Why the last change was not recorded, if it was not. */
  error: string | null;
  /** Holds the progress `change` returns for project `of`, or why it failed. */
  change(change: Promise<ProjectProgress>, of: string): void;
  /** Holds `progress` as the latest for project `of`. */
  set(of: string, progress: ProjectProgress): void;
}

export function useProjectProgress(
  projectId: string | null,
  turnCount: number,
): ProjectProgressRead {
  const projectApi = useProjectApi();
  const { latest, set } = useResource(
    projectId,
    (of, signal) => projectApi.progress(of, signal),
    turnCount,
  );
  const [error, setError] = useState<string | null>(null);
  const change = useCallback(
    (changing: Promise<ProjectProgress>, of: string) => {
      changing.then(
        (progress) => {
          setError(null);
          set(of, progress);
        },
        (e: unknown) => setError(errorMessage(e)),
      );
    },
    [set],
  );
  return { progress: latest, error, change, set };
}
