/**
 * The build's identity in the footer: the version and the short commit the app was deployed from.
 *
 * It says nothing while the build is unknown or the server cannot be asked, since a footer is no
 * place for an error.
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
    <p className="app-footer-build" title={about.commit ?? undefined}>
      Build <code>{describeBuild(about)}</code>
    </p>
  );
}
