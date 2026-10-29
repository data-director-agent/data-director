/**
 * Who is signed in, behind one interface so tests can stand in for the server (ADR-0029).
 *
 * The server decides who a request acts for; the shell only shows it. `GET /api/session` says
 * whether this server signs anyone in, who is signed in and when their session ends, and does not
 * keep the session going. `POST /api/session` keeps it going ("Stay signed in"). Any other API
 * call that answers `401` means the session has ended: `checkSignedIn` says so to the page, which
 * then shows the sign-in page.
 */

import { createContext, useContext } from "react";

export interface SessionPrincipal {
  principalId: string;
  name: string;
  assurance: string;
  vouchedBy?: string;
}

export interface Session {
  /** False on a development server, where every run acts for the operator. */
  signsIn: boolean;
  /** The identity provider people sign in with (its issuer IRI), or null. */
  issuer: string | null;
  principal: SessionPrincipal | null;
  /** When the session ends if nothing more is done in it (ISO 8601), or null. */
  expiresAt: string | null;
}

export interface RawSession {
  signs_in: boolean;
  issuer: string | null;
  principal: {
    principal_id: string;
    name: string;
    assurance: string;
    vouched_by?: string;
  } | null;
  expires_at: string | null;
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
        }
      : null,
    expiresAt: raw.expires_at,
  };
}

async function session(response: Response): Promise<Session> {
  if (!response.ok) throw new Error(`the server answered ${response.status}`);
  return fromRaw((await response.json()) as RawSession);
}

export const httpSessionApi: SessionApi = {
  async get(signal) {
    return session(await fetch("/api/session", signal ? { signal } : {}));
  },
  async stay() {
    return session(await fetch("/api/session", { method: "POST" }));
  },
  async signOut() {
    const response = await fetch("/api/sign-out", { method: "POST" });
    if (!response.ok) throw new Error(`the server answered ${response.status}`);
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
export function assuranceText({ assurance, vouchedBy }: Pick<SessionPrincipal, "assurance" | "vouchedBy">): string {
  if (assurance === "asserted") return "asserted by the operator, not authenticated";
  if (assurance === "authenticated" && vouchedBy) {
    return `authenticated by ${hostOf(vouchedBy)}`;
  }
  return assurance;
}

/**
 * The provider's name for a person to recognise: "ORCID" for ORCID and its sandbox (ADR-0029),
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
