/** A stand-in for the session endpoints, and the sessions the shell's tests start from. */

import type { ReactNode } from "react";

import { type Session, type SessionApi, SessionApiContext } from "../session/api";

export const DEVELOPMENT: Session = {
  signsIn: false,
  issuer: null,
  principal: {
    principalId: "https://orcid.org/0000-0002-1825-0097",
    name: "Josiah Carberry",
    assurance: "asserted",
  },
  expiresAt: null,
};

export const SIGNED_OUT: Session = {
  signsIn: true,
  issuer: "https://sandbox.orcid.org",
  principal: null,
  expiresAt: null,
};

export function signedIn(expiresAt = new Date(Date.now() + 8 * 3600_000).toISOString()): Session {
  return {
    signsIn: true,
    issuer: "https://sandbox.orcid.org",
    principal: {
      principalId: "https://sandbox.orcid.org/0000-0002-1825-0097",
      name: "Josiah Carberry",
      assurance: "authenticated",
      vouchedBy: "https://sandbox.orcid.org",
    },
    expiresAt,
  };
}

export function fakeSessionApi(session: Session, overrides: Partial<SessionApi> = {}): SessionApi {
  return {
    get: () => Promise.resolve(session),
    stay: () => Promise.resolve(session),
    signOut: () => Promise.resolve(),
    ...overrides,
  };
}

export function WithSession({ api, children }: { api: SessionApi; children: ReactNode }) {
  return <SessionApiContext.Provider value={api}>{children}</SessionApiContext.Provider>;
}
