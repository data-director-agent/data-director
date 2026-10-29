/**
 * The page frame: a skip link, the banner and one main landmark, then a footer that names the build.
 *
 * The banner holds the same things on every page (the name, the main navigation, who is signed
 * in and the dark mode switch), so nothing in it moves when the page changes. What a page is
 * about, and for whom it acts, is said in the page itself.
 */

import "./Frame.css";

import type { ReactNode } from "react";

import { Link } from "../../route";
import { FooterBuild } from "./FooterBuild";
import { ThemeSwitch } from "./ThemeSwitch";

const PAGES = [
  { to: "/", label: "Conversation" },
  { to: "/agents", label: "Agents" },
] as const;

const USER_GUIDE = "https://data-director-agent.github.io/data-director/user-guide/";

/**
 * `from` is the page the reader is on, which the report form carries so a report says where it
 * was made. `account` is who is signed in (`session/Account`).
 */
export function Frame({
  current,
  from = current,
  account,
  children,
}: {
  current: string;
  from?: string;
  account?: ReactNode;
  children: ReactNode;
}) {
  const run = new URLSearchParams(from.split("?")[1]).get("run");
  const report = `/feedback?from=${encodeURIComponent(from)}${run ? `&run=${encodeURIComponent(run)}` : ""}`;
  return (
    <>
      <a className="skip-link" href="#main">
        Skip to main content
      </a>
      <header className="app-header">
        <div className="app-header-inner">
          <p className="app-brand">
            Data Director <span className="status status-warn">Alpha</span>
          </p>
          <nav aria-label="Main" className="app-nav">
            <ul className="app-nav-list">
              {PAGES.map(({ to, label }) => (
                <li key={to}>
                  <Link
                    to={to}
                    className="app-nav-link"
                    {...(to === current ? { "aria-current": "page" as const } : {})}
                  >
                    {label}
                  </Link>
                </li>
              ))}
            </ul>
          </nav>
          <div className="app-tools">
            {account}
            <a className="app-tool-link" href={USER_GUIDE} target="_blank" rel="noreferrer">
              User guide
            </a>
            <Link
              to={report}
              className="app-tool-link"
              {...(current === "/feedback" ? { "aria-current": "page" as const } : {})}
            >
              Report a problem
            </Link>
            <ThemeSwitch />
          </div>
        </div>
      </header>
      <main id="main" className="app-main" tabIndex={-1}>
        {children}
      </main>
      <footer className="app-footer">
        <div className="app-footer-inner">
          <FooterBuild />
        </div>
      </footer>
    </>
  );
}
