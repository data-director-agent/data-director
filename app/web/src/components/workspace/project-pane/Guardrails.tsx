/**
 * The limits Data Director works within in this project, closed by default because it is reference
 * rather than something to act on: what this deployment's policy lets it do at each step (#448),
 * then the project's own flags, which are not built (#72, #39).
 */

import { Link } from "../../../route";
import { IssueLinks } from "../../NotBuilt";

const NOT_BUILT: { label: string; issues: number[] }[] = [
  { label: "Approval before an agent acts", issues: [72] },
  { label: "Pause for personal data", issues: [39] },
];

export function Guardrails() {
  return (
    <section aria-labelledby="guardrails-heading" className="pane-section">
      <details className="pane-details">
        <summary>
          <h3 id="guardrails-heading">Guardrails</h3>
        </summary>
        <p>
          <Link to="/policy#policy-steps">What Data Director may do at each step</Link>
        </p>
        <dl className="pane-facts">
          {NOT_BUILT.map(({ label, issues }) => (
            <div key={label}>
              <dt>{label}</dt>
              <dd>
                <span className="status status-undeclared">Not built yet</span> (<IssueLinks issues={issues} />)
              </dd>
            </div>
          ))}
        </dl>
      </details>
    </section>
  );
}
