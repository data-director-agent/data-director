/**
 * The page frame: a skip link, the banner and one main landmark, then a footer that names the build.
 *
 * The banner holds the same things on every page (the name, the main navigation, who is signed
 * in, the and the settings), so nothing in it moves when the page changes.
 * What a page is about, and for whom it acts, is said in the page itself. The page's two live regions are
 * mounted here, once, so they are present from load (`ui/Announcer`).
 */

import "./Frame.css";

import {
  Activity,
  BookOpen,
  Bot,
  Bug,
  FolderOpen,
  Map as MapIcon,
  MessagesSquare,
  Settings as SettingsIcon,
  Shield,
  type LucideIcon,
} from "lucide-react";
import type { ReactNode } from "react";

import { Link } from "../../route";
import { AnnouncerProvider } from "../ui/Announcer";
import { FooterBuild } from "./FooterBuild";

// Projects first: the project is the unit of work that the rest belongs to (docs/specs/app.md).
// `/project` opens the current project's page, or the list of projects when none is current.
// The journey map follows it, as the project's place in the process is the next thing a person
// looks for; `/journey` opens the current project's map. The conversation stays the page a
// person lands on, so nobody must make a project first.
const PAGES: readonly { to: string; label: string; icon: LucideIcon }[] = [
  { to: "/project", label: "Projects", icon: FolderOpen },
  { to: "/journey", label: "Journey map", icon: MapIcon },
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
const SITE = "https://data-director-agent.github.io/data-director/";
const CONTRIBUTING =
  "https://github.com/data-director-agent/data-director/blob/main/CONTRIBUTING.md";

// The project's own pages. The privacy notice here covers the project's website, not an
// instance, so it is labelled as the project's and the operator's notice stays in the build line.
const PROJECT_LINKS: readonly { href: string; label: string }[] = [
  { href: SITE, label: "About" },
  { href: `${SITE}privacy/`, label: "Project privacy notice" },
  { href: CONTRIBUTING, label: "Contribute" },
];

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
    <AnnouncerProvider>
      <a className="skip-link" href="#main">
        Skip to main content
      </a>
      <header className="app-header">
        <div className="app-header-inner">
          <p className="app-brand">
            <Link to="/" className="app-brand-link">
              Data Director
            </Link>{" "}
            <span className="status status-warn">Alpha</span>
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
            <span className="app-account">{account}</span>
            <a
              className="app-tool-link"
              href={USER_GUIDE}
              target="_blank"
              rel="noreferrer"
            >
              <BannerIcon icon={BookOpen} />
              User guide
              <span className="visually-hidden"> (opens in a new tab)</span>
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
            <Link
              to="/settings"
              className="app-tool-link"
              {...(current === "/settings"
                ? { "aria-current": "page" as const }
                : {})}
            >
              <BannerIcon icon={SettingsIcon} />
              Settings
            </Link>
          </div>
        </div>
      </header>
      <main id="main" className="app-main" tabIndex={-1}>
        {children}
      </main>
      <footer className="app-footer">
        <div className="app-footer-inner">
          <div className="app-footer-partners">
            <p className="app-footer-support">Supported by</p>
            <ul className="app-footer-logos">
              <li>
                <a
                  className="app-footer-logo-link"
                  href={SHEFFIELD}
                  target="_blank"
                  rel="noreferrer"
                >
                  <img
                    className="app-footer-logo"
                    src="/logos/university-of-sheffield.svg"
                    alt="The University of Sheffield"
                    width={497}
                    height={200}
                  />
                  <span className="visually-hidden"> (opens in a new tab)</span>
                </a>
              </li>
              <li>
                <a
                  className="app-footer-logo-link"
                  href={RDA}
                  target="_blank"
                  rel="noreferrer"
                >
                  <img
                    className="app-footer-logo"
                    src="/logos/research-data-alliance.png"
                    alt="Research Data Alliance"
                    width={640}
                    height={384}
                  />
                  <span className="visually-hidden"> (opens in a new tab)</span>
                </a>
              </li>
            </ul>
          </div>
          <div className="app-footer-details">
            <nav aria-label="Footer" className="app-footer-nav">
              <ul className="app-footer-links">
                {PROJECT_LINKS.map(({ href, label }) => (
                  <li key={href}>
                    <a href={href} target="_blank" rel="noreferrer">
                      {label}
                      <span className="visually-hidden">
                        {" "}
                        (opens in a new tab)
                      </span>
                    </a>
                  </li>
                ))}
              </ul>
            </nav>
            <p className="app-footer-about">
              A reference implementation of the{" "}
              <a href={BLUEPRINT} target="_blank" rel="noreferrer">
                RDA Data Director Agentic AI Blueprint
                <span className="visually-hidden"> (opens in a new tab)</span>
              </a>
              . Open source under the MIT licence:{" "}
              <a href={SOURCE} target="_blank" rel="noreferrer">
                view the code
                <span className="visually-hidden"> (opens in a new tab)</span>
              </a>
              .
            </p>
            <FooterBuild />
          </div>
        </div>
      </footer>
    </AnnouncerProvider>
  );
}
