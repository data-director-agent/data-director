/**
 * The organisation behind a funder a project names, as the pinned ROR dump records it
 * (`GET /api/funders/ror/{id}`, docs/specs/app.md), behind one interface so tests can stand in for
 * the server.
 */

import { createContext, useContext } from "react";

import type { RorOrganisation } from "../api/generated/responses";
import { json } from "../http";

export type { RorOrganisation };

/** The dump holds no organisation at the identifier given (a 404). */
export class OrganisationNotFound extends Error {}

export interface FundersApi {
  organisation(rorId: string, signal?: AbortSignal): Promise<RorOrganisation>;
}

export const httpFundersApi: FundersApi = {
  async organisation(rorId, signal) {
    const response = await fetch(`/api/funders/ror/${encodeURIComponent(rorId)}`, signal ? { signal } : {});
    return json<RorOrganisation>(response, (status, problem) =>
      status === 404 && problem ? new OrganisationNotFound(problem.detail ?? problem.title) : null,
    );
  },
};

export const FundersApiContext = createContext<FundersApi>(httpFundersApi);

export function useFundersApi(): FundersApi {
  return useContext(FundersApiContext);
}

/** The name ROR displays for `organisation`: its display name, else its label, else its first. */
export function displayName(organisation: RorOrganisation): string {
  for (const wanted of ["ror_display", "label"]) {
    const found = organisation.names.find((name) => name.types.includes(wanted));
    if (found) return found.value;
  }
  return organisation.names[0]?.value ?? organisation.ror_id;
}
