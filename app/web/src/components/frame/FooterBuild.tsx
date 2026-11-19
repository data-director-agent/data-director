/**
 * What the footer learns from the server: the build's identity (the version and the short commit
 * the app was deployed from) and a link to the operator's privacy notice, when it has one.
 *
 * It says nothing while the server cannot be asked, since a footer is no place for an error, and
 * shows no privacy link unless the operator set one: the project's own notice covers its website,
 * not an instance, so there is nothing to fall back to (docs/specs/app.md).
 */

import { useEffect, useState } from "react";

import { type About, describeBuild, useFeedbackApi } from "../../feedback/api";

export function FooterBuild() {
  const api = useFeedbackApi();
  const [about, setAbout] = useState<About | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    api
      .about(controller.signal)
      .then(setAbout)
      .catch(() => undefined);
    return () => controller.abort();
  }, [api]);

  if (!about) return null;
  return (
    <p className="app-footer-meta">
      {about.privacy_notice_url ? (
        <span className="app-footer-privacy">
          <a href={about.privacy_notice_url} target="_blank" rel="noreferrer">
            Privacy notice
            <span className="visually-hidden"> (opens in a new tab)</span>
          </a>
        </span>
      ) : null}
      <span className="app-footer-build" title={about.commit ?? undefined}>
        Build <code>{describeBuild(about)}</code>
      </span>
    </p>
  );
}
