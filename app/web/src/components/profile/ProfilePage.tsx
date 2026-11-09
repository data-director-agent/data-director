/**
 * Who Data Director takes the signed-in person to be: the name and iD that ORCID gave at sign-in,
 * how the identity was confirmed and when the session ends. Nothing else is held about a person
 * (docs/specs/policy-and-identity.md), and the page says so.
 */

import "./ProfilePage.css";

import { ExternalLink } from "lucide-react";

import { Link } from "../../route";
import { type Session, assuranceText, providerName } from "../../session/api";
import { PageHeader } from "../frame/PageHeader";
import { OrcidIcon } from "../ui/BrandIcon";

const ORCID_ID = /^\d{4}-\d{4}-\d{4}-\d{3}[\dX]$/;

/** The last part of an identifier such as `https://orcid.org/0000-…`. */
function identifierOf(principalId: string): string {
  return principalId.split("/").filter(Boolean).pop() ?? principalId;
}

export function ProfilePage({ session }: { session: Session }) {
  const { principal } = session;
  if (!principal) return null;

  const provider = providerName(session.issuer);
  const profile = ORCID_ID.test(identifierOf(principal.principalId)) ? principal.principalId : null;
  const expires = session.expiresAt ? new Date(session.expiresAt) : null;

  return (
    <>
      <PageHeader title="Your profile" />
      {!session.signsIn && (
        <p className="callout status-warn">
          This server does not sign anyone in. Every run acts for the operator, shown below.
        </p>
      )}
      <dl className="profile-details">
        <div>
          <dt>Name</dt>
          <dd>{principal.name}</dd>
        </div>
        <div>
          <dt>{profile ? "ORCID iD" : "Identifier"}</dt>
          <dd>
            {profile ? (
              <a href={profile} rel="noreferrer">
                <OrcidIcon className="brand-icon" />{" "}
                {profile}
                <span className="visually-hidden"> (your public ORCID record)</span>{" "}
                <ExternalLink className="app-icon" size="1em" aria-hidden="true" />
              </a>
            ) : (
              principal.principalId
            )}
          </dd>
        </div>
        <div>
          <dt>How you are known</dt>
          <dd>{assuranceText(principal)}</dd>
        </div>
        {session.signsIn && expires && (
          <div>
            <dt>Session ends</dt>
            <dd>
              <time dateTime={expires.toISOString()}>{expires.toLocaleString()}</time>
            </dd>
          </div>
        )}
      </dl>
      <p>
        {session.signsIn
          ? `Data Director asks ${provider} for your iD and your name only. It keeps no email address, no biography and no access to your ${provider} record. To change what ${provider} says about you, edit your record there.`
          : "No sign-in provider is configured, so nothing here came from a person’s own record."}
      </p>
      <p>
        <Link to="/">Back to the conversation</Link>
      </p>
    </>
  );
}
