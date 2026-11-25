/**
 * The credit each external source asks for (`GET /api/sources`, `app/config/credits.yaml`).
 *
 * The shell reads the list once and names an evidence item's source from it, by the prefixes the
 * list gives. It decides nothing from the list: it is a record of other people's terms, drawn.
 */

import { createContext, useContext } from "react";

import type { Sources, SourceCredit } from "../api/generated/responses";
import { serverAnswered } from "../status";

export type { SourceCredit } from "../api/generated/responses";

/** The credit list, open to everyone, so the sign-in page can show it too. */
export async function fetchSources(signal?: AbortSignal): Promise<SourceCredit[]> {
  const response = await fetch("/api/sources", signal ? { signal } : {});
  if (!response.ok) throw new Error(serverAnswered(response.status));
  return ((await response.json()) as Sources).sources;
}

/** The source an evidence item is from, or null where the list does not say. */
export function creditFor(
  item: { source_id: string; snapshot_ref?: string | null },
  sources: readonly SourceCredit[],
): SourceCredit | null {
  const ref = item.snapshot_ref ?? "";
  return (
    sources.find(
      ({ match }) =>
        match.source_id_prefixes.some((prefix) => item.source_id.startsWith(prefix)) ||
        (ref !== "" && match.snapshot_ref_prefixes.some((prefix) => ref.startsWith(prefix))),
    ) ?? null
  );
}

export const SourceCreditsContext = createContext<readonly SourceCredit[]>([]);

export function useSourceCredits(): readonly SourceCredit[] {
  return useContext(SourceCreditsContext);
}
