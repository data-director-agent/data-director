/**
 * Where a person lands once they have signed out. Signing out ends the session on the server,
 * but the provider offers no sign-out for the app, so the person may still be signed in there,
 * and the page says so (ADR-0029).
 */

import "./Session.css";

import { PageHeader } from "../frame/PageHeader";
import { providerName, signInHref } from "../../session/api";

export function SignedOutPage({ issuer }: { issuer: string | null }) {
  const provider = providerName(issuer);
  return (
    <>
      <PageHeader title="You have signed out" />
      <div className="session-page">
        <p>Your session with Data Director has ended. Nothing more is done in your name here.</p>
        <p>
          You may still be signed in at {provider}. On a shared computer, sign out there as well,
          or close the browser.
        </p>
        <p>
          <a href={signInHref("/")}>Sign in again</a>
        </p>
      </div>
    </>
  );
}
