/**
 * Where this work stands: whom it acts for, whose rules apply, and (once there is a record of
 * the project) its dataset, phase, repository and open governance flags. Until then those four
 * are drawn as not built, linked to their issues, with no value standing in for them.
 *
 * The principal is the signed-in person, with who vouched for them, or on a development server
 * the operator's assertion, and the bar says which (ADR-0029).
 */

import "./StatusBar.css";

import type { Directory } from "../../manifest/normalise";
import { assuranceText } from "../../session/api";
import { IssueLinks } from "../NotBuilt";

const NOT_BUILT: { label: string; issues: number[] }[] = [
  { label: "Dataset", issues: [160] },
  { label: "Phase", issues: [160] },
  { label: "Repository", issues: [160] },
  // TODO(#72, #39): governance flags have no single issue; the review gate and the
  // personal-data pause are the nearest.
  { label: "Governance", issues: [72, 39] },
];

export function StatusBar({ directory }: { directory: Directory }) {
  const { actingFor, profileRef } = directory;
  return (
    <section aria-label="Where this work stands" className="status-bar">
      <dl>
        <div>
          <dt>Acting for</dt>
          <dd>
            {actingFor.name} ({assuranceText(actingFor)})
          </dd>
        </div>
        <div>
          <dt>Policy</dt>
          <dd>
            <code>{profileRef}</code>
          </dd>
        </div>
        {NOT_BUILT.map(({ label, issues }) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd>
              <span className="status status-undeclared">Not built yet</span> (
              <IssueLinks issues={issues} />)
            </dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
