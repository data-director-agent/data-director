/**
 * The page frame: a skip link, the banner and one main landmark.
 *
 * The banner says whom runs act for and whose rules apply. Until there is authentication
 * (ADR-0018, #17) the principal is the operator's assertion, and the banner says so.
 */

import type { ReactNode } from "react";

export interface FrameContext {
  actingFor: { name: string; assurance: string };
  profileRef: string;
}

export function Frame({ context, children }: { context?: FrameContext; children: ReactNode }) {
  return (
    <>
      <a className="skip-link" href="#main">
        Skip to main content
      </a>
      <header className="site-header">
        <p className="site-name">
          Data Director <span className="status status-warn">Alpha</span>
        </p>
        {context && (
          <p className="site-context">
            Acting as {context.actingFor.name} (
            {context.actingFor.assurance === "asserted"
              ? "asserted by the operator, not authenticated"
              : context.actingFor.assurance}
            ) · Policy <code>{context.profileRef}</code>
          </p>
        )}
      </header>
      <main id="main" tabIndex={-1}>
        {children}
      </main>
    </>
  );
}
