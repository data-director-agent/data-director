/**
 * The page frame: a skip link, the banner and one main landmark, then a footer that names the build.
 *
 * The banner holds the same things on every page (the name, the main navigation, who is signed
 * in and the dark mode switch), so nothing in it moves when the page changes. What a page is
 * about, and for whom it acts, is said in the page itself.
 */

import "./Frame.css";

import {
  Activity,
  BookOpen,
  Bot,
  Bug,
  FolderOpen,
  MessagesSquare,
  Shield,
  type LucideIcon,
} from "lucide-react";
import type { ReactNode } from "react";

import { Link } from "../../route";
import { FooterBuild } from "./FooterBuild";
import { ThemeSwitch } from "./ThemeSwitch";

// Projects first: the project is the unit of work that the rest belongs to (docs/specs/app.md).
// The conversation stays the page a person lands on, so nobody must make a project first.
const PAGES: readonly { to: string; label: string; icon: LucideIcon }[] = [
  { to: "/projects", label: "Projects", icon: FolderOpen },
  { to: "/", label: "Conversation", icon: MessagesSquare },
  { to: "/activity", label: "Activity log", icon: Activity },
  { to: "/agents", label: "Agents", icon: Bot },
  { to: "/policy", label: "Policy", icon: Shield },
];

/** A banner icon: decoration beside a label that says the same, so hidden from screen readers. */
function BannerIcon({ icon: Icon }: { icon: LucideIcon }) {
  return <Icon className="app-icon" size="1.125em" aria-hidden="true" />;
}

const SHEFFIELD = "https://www.sheffield.ac.uk/";
const RDA = "https://www.rd-alliance.org/";
const BLUEPRINT = "https://doi.org/10.15497/RDA00157";
const SOURCE = "https://github.com/data-director-agent/data-director";
const USER_GUIDE =
  "https://data-director-agent.github.io/data-director/user-guide/";

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
              {PAGES.map(({ to, label, icon }) => (
                <li key={to}>
                  <Link
                    to={to}
                    className="app-nav-link"
                    {...(to === current
                      ? { "aria-current": "page" as const }
                      : {})}
                  >
                    <BannerIcon icon={icon} />
                    {label}
                  </Link>
                </li>
              ))}
            </ul>
          </nav>
          <div className="app-tools">
            {account}
            <a
              className="app-tool-link"
              href={USER_GUIDE}
              target="_blank"
              rel="noreferrer"
            >
              <BannerIcon icon={BookOpen} />
              User guide
            </a>
            <Link
              to={report}
              className="app-tool-link"
              {...(current === "/feedback"
                ? { "aria-current": "page" as const }
                : {})}
            >
              <BannerIcon icon={Bug} />
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
          <p className="app-footer-support">
            Supported by{" "}
            <a href={SHEFFIELD} target="_blank" rel="noreferrer">
              The University of Sheffield
            </a>{" "}
            and the{" "}
            <a href={RDA} target="_blank" rel="noreferrer">
              Research Data Alliance
            </a>{" "}
            (RDA).
          </p>
          <p className="app-footer-about">
            A reference implementation of the{" "}
            <a href={BLUEPRINT} target="_blank" rel="noreferrer">
              RDA Data Director Agentic AI Blueprint
            </a>
            . Open source under the MIT licence:{" "}
            <a href={SOURCE} target="_blank" rel="noreferrer">
              view the code
            </a>
            .
          </p>
          <FooterBuild />
        </div>
      </footer>
    </>
  );
}
