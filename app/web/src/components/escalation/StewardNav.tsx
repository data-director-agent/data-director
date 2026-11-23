/**
 * The two pages of a data steward's workspace (docs/ui/steward-escalation-flows.md, flow C): the
 * requests routed to their teams, and the projects they may see. The current one is marked.
 */

import { Link } from "../../route";

const PAGES = [
  { to: "/steward", label: "Requests" },
  { to: "/steward/projects", label: "Projects" },
] as const;

export function StewardNav({ current }: { current: (typeof PAGES)[number]["to"] }) {
  return (
    <nav aria-label="Data steward" className="steward-nav">
      <ul className="plain-list">
        {PAGES.map((page) => (
          <li key={page.to}>
            <Link to={page.to} {...(page.to === current ? { "aria-current": "page" as const } : {})}>
              {page.label}
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}
