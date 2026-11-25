/**
 * The metadata standard a project's record is drafted and checked in
 * (`/api/projects/{id}/repository/standard`, docs/specs/deposit.md, invariant 5): the standard of
 * the repository chosen last and why, the standards the deployment has a set for, and a person's
 * choice of another. The server refuses a standard the repository's own settings are not written
 * for; the page offers a choice only when it may be made.
 */

import type {
  ChosenStandard,
  StandardChoice,
} from "../api/generated/responses";
import { json } from "../http";

export type {
  ChosenStandard,
  StandardChoice,
} from "../api/generated/responses";

function standardPath(projectId: string): string {
  return `/api/projects/${encodeURIComponent(projectId)}/repository/standard`;
}

/** The standard of the repository chosen last and what may be chosen; null while none is. */
export async function standardChoice(
  projectId: string,
  signal?: AbortSignal,
): Promise<StandardChoice | null> {
  const response = await fetch(
    standardPath(projectId),
    signal ? { signal } : {},
  );
  if (response.status === 404) return null;
  return json<StandardChoice>(response);
}

/** Choose the standard named by `conformsTo` for the repository chosen last. */
export async function chooseStandard(
  projectId: string,
  conformsTo: string,
): Promise<StandardChoice> {
  const response = await fetch(standardPath(projectId), {
    method: "PUT",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ conforms_to: conformsTo }),
  });
  return json<StandardChoice>(response);
}

/** Why the record is in this standard, in words, ending without a full stop. */
export function reasonInWords(standard: ChosenStandard): string {
  switch (standard.reason) {
    case "override":
      return "this deployment's settings for the repository name it";
    case "chosen":
      return standard.chosen_by
        ? `${standard.chosen_by} chose it`
        : "a person on the project chose it";
    case "declared":
      return "it is the standard the repository's re3data record lists";
    case "declared_several":
      return "the repository's re3data record lists several standards, and this is the deployment's first preference among them";
    case "fallback":
      return "assumed: the repository's re3data record lists no standard this deployment has a set for, so DataCite's is used, which any repository that mints DataCite DOIs accepts";
  }
}
