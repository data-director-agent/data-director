/**
 * The page a person sees when the server signs people in and they are not signed in (ADR-0029).
 *
 * Signing in is a real link to the server, which sends the browser to the provider and back; the
 * shell holds no token and decides nothing about identity. A sign-in that came back without a
 * session lands here with `?problem=` naming why, and the page says so.
 */

import "./Session.css";

import { PageHeader } from "../frame/PageHeader";
import { providerName, signInHref } from "../../session/api";

const PROBLEMS: Record<string, string> = {
  declined: "You did not sign in, so nothing has changed. You can try again.",
  failed:
    "Signing in did not work. The sign-in may have taken too long, or been started in another " +
    "browser. Please try again.",
};

export function SignInPage({
  issuer,
  returnTo,
  problem,
}: {
  issuer: string | null;
  returnTo: string;
  problem?: string | null | undefined;
}) {
  const provider = providerName(issuer);
  return (
    <>
      <PageHeader title="Sign in to Data Director" />
      {problem && (
        <div role="alert" className="callout status-danger">
          <p>{PROBLEMS[problem] ?? PROBLEMS.failed}</p>
        </div>
      )}
      <div className="session-page">
        <p>
          Data Director records who each piece of work is done for. Sign in with your {provider}{" "}
          iD so that the work you do here is recorded as yours.
        </p>
        <p>
          You will go to {provider} to sign in, then come back here. Data Director asks {provider}{" "}
          for your iD and your name only, not for your email address.
        </p>
        <p>
          <a className="button button-primary" href={signInHref(returnTo)}>
            Sign in with {provider}
          </a>
        </p>
      </div>
    </>
  );
}
