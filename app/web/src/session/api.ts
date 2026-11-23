/**
 * Who is signed in, behind one interface so tests can stand in for the server (docs/specs/policy-and-identity.md).
 *
 * The server decides who a request acts for; the shell only shows it. `GET /api/session` says
 * whether this server signs anyone in, who is signed in and when their session ends, and does not
 * keep the session going. `POST /api/session` keeps it going ("Stay signed in"). Any other API
 * call that answers `401` means the session has ended: `checkSignedIn` says so to the page, which
 * then shows the sign-in page.
 */

import { createContext, useContext } from "react";

import type { RawSession } from "../api/generated/responses";
import { serverAnswered } from "../status";

export type { RawSession } from "../api/generated/responses";

/** A steward team the person is in, as the deployment's profile names it (docs/specs/stewardship.md). */
export interface StewardTeam {
  teamId: string;
  name: string;
  /** The address the team is emailed at, if the profile names one, and what it is told about
   * there (docs/specs/stewardship.md, invariant 13). */
  notify?: string;
  notifyOn: string[];
}

export interface SessionPrincipal {
  principalId: string;
  name: string;
  assurance: string;
  vouchedBy?: string;
  /** The person's deployment roles, from the profile. Everyone is a researcher; the shell only
   * shows them, and the harness decides what each may do. */
  roles: ("researcher" | "steward" | "administrator")[];
  /** The steward teams the person is in; empty unless they are a steward. */
  teams: StewardTeam[];
}

/** A provider a person's own model account may be with, and the base URL origins it may name. */
export interface ModelAccountProvider {
  provider: string;
  /** Origins (`https://host[:port]`); listed only for `openai-compatible`, which must name one. */
  baseUrls: string[];
}

export interface Session {
  /** False on a development server, where every run acts for the operator. */
  signsIn: boolean;
  /** The identity provider people sign in with (its issuer IRI), or null. */
  issuer: string | null;
  principal: SessionPrincipal | null;
  /** When the session ends if nothing more is done in it (ISO 8601), or null. */
  expiresAt: string | null;
  /** Whether a person may add their own model account on the Settings page (docs/specs/model-accounts.md). */
  modelAccounts: boolean;
  /** The providers the profile lets a person's own account be with; empty unless `modelAccounts`. */
  modelAccountProviders: ModelAccountProvider[];
  /** Whether a person may connect their own repository account, to deposit a draft through the
   * repository's API (docs/specs/deposit.md). */
  repositoryAccounts: boolean;
}

export interface SessionApi {
  get(signal?: AbortSignal): Promise<Session>;
  stay(): Promise<Session>;
  signOut(): Promise<void>;
}

export function fromRaw(raw: RawSession): Session {
  const p = raw.principal;
  return {
    signsIn: raw.signs_in,
    issuer: raw.issuer,
    principal: p
      ? {
          principalId: p.principal_id,
          name: p.name,
          assurance: p.assurance,
          ...(p.vouched_by ? { vouchedBy: p.vouched_by } : {}),
          roles: p.roles,
          teams: p.teams.map((t) => ({
            teamId: t.team_id,
            name: t.name,
            ...(t.notify === undefined ? {} : { notify: t.notify }),
            notifyOn: t.notify_on,
          })),
        }
      : null,
    expiresAt: raw.expires_at,
    modelAccounts: raw.model_accounts,
    modelAccountProviders: raw.model_account_providers.map((p) => ({
      provider: p.provider,
      baseUrls: p.base_urls,
    })),
    repositoryAccounts: raw.repository_accounts,
  };
}

async function session(response: Response): Promise<Session> {
  if (!response.ok) throw new Error(serverAnswered(response.status));
  return fromRaw((await response.json()) as RawSession);
}

// The server refuses a request that changes state unless it declares JSON, body or not (#728).
const JSON_HEADERS = { "content-type": "application/json" };

export const httpSessionApi: SessionApi = {
  async get(signal) {
    return session(await fetch("/api/session", signal ? { signal } : {}));
  },
  async stay() {
    return session(
      await fetch("/api/session", { method: "POST", headers: JSON_HEADERS }),
    );
  },
  async signOut() {
    const response = await fetch("/api/sign-out", {
      method: "POST",
      headers: JSON_HEADERS,
    });
    if (!response.ok) throw new Error(serverAnswered(response.status));
  },
};

export const SessionApiContext = createContext<SessionApi>(httpSessionApi);

export function useSessionApi(): SessionApi {
  return useContext(SessionApiContext);
}

/** Fired on `window` when the server says the session has ended (or on signing out). */
export const SIGNED_OUT = "dd-signed-out";

/** The request was refused because nobody is signed in. */
export class SignedOut extends Error {
  constructor() {
    super("you are not signed in");
  }
}

/** Throws `SignedOut`, and tells the page, if `response` is a `401`. Every API call checks. */
export function checkSignedIn(response: Response): void {
  if (response.status !== 401) return;
  window.dispatchEvent(new Event(SIGNED_OUT));
  throw new SignedOut();
}

/** Where to start signing in, coming back to `returnTo` afterwards. */
export function signInHref(returnTo: string): string {
  return `/api/sign-in?return_to=${encodeURIComponent(returnTo)}`;
}

/**
 * How sure the record is of whom it acts for, in words: who vouched for an authenticated person,
 * or that the operator asserted it.
 */
export function assuranceText({
  assurance,
  vouchedBy,
}: Pick<SessionPrincipal, "assurance" | "vouchedBy">): string {
  if (assurance === "asserted")
    return "asserted by the operator, not authenticated";
  if (assurance === "authenticated" && vouchedBy) {
    return `authenticated by ${hostOf(vouchedBy)}`;
  }
  return assurance;
}

/**
 * The provider's name for a person to recognise: "ORCID" for ORCID and its sandbox (docs/specs/policy-and-identity.md),
 * otherwise the issuer's host. The shell names no provider of its own accord.
 */
export function providerName(issuer: string | null): string {
  if (!issuer) return "your identity provider";
  const host = hostOf(issuer);
  return host === "orcid.org" || host.endsWith(".orcid.org") ? "ORCID" : host;
}

function hostOf(iri: string): string {
  try {
    return new URL(iri).host;
  } catch {
    return iri;
  }
}
