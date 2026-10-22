/**
 * The page frame: a skip link, the banner (with the dark mode switch) and one main landmark.
 *
 * The banner says whom runs act for and whose rules apply. Until there is authentication
 * (ADR-0018, #17) the principal is the operator's assertion, and the banner says so.
 */

import type { ReactNode } from "react";

import { Link } from "../../route";
import { ThemeSwitch } from "./ThemeSwitch";

export interface FrameContext {
  actingFor: { name: string; assurance: string };
  profileRef: string;
}

export function Frame({
  context,
  onAgents = false,
  children,
}: {
  context?: FrameContext;
  onAgents?: boolean;
  children: ReactNode;
}) {
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
        <nav aria-label="Main">
          <Link to="/" {...(onAgents ? {} : { "aria-current": "page" as const })}>
            Conversation
          </Link>{" "}
          <Link to="/agents" {...(onAgents ? { "aria-current": "page" as const } : {})}>
            Agents
          </Link>
        </nav>
        <ThemeSwitch />
      </header>
      <main id="main" tabIndex={-1}>
        {children}
      </main>
    </>
  );
}
