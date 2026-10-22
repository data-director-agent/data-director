/**
 * The page frame: a skip link, the banner and one main landmark.
 *
 * The banner holds the same three things on every page (the name, the main navigation and the
 * dark mode switch), so nothing in it moves when the page changes. What a page is about, and for
 * whom it acts, is said in the page itself.
 */

import "./Frame.css";

import type { ReactNode } from "react";

import { Link } from "../../route";
import { ThemeSwitch } from "./ThemeSwitch";

const PAGES = [
  { to: "/", label: "Conversation" },
  { to: "/agents", label: "Agents" },
] as const;

export function Frame({ current, children }: { current: string; children: ReactNode }) {
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
            <ThemeSwitch />
          </div>
        </div>
      </header>
      <main id="main" className="app-main" tabIndex={-1}>
        {children}
      </main>
    </>
  );
}
