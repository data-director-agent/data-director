/**
 * Where this work stands: whom it acts for, whose rules apply, and (once there is a record of
 * the project) its dataset, phase, repository and open governance flags. Until then those four
 * are drawn as not built, linked to their issues, with no value standing in for them.
 *
 * Until there is authentication (ADR-0018, #17) the principal is the operator's assertion, and
 * the bar says so.
 */

import type { Directory } from "../../manifest/normalise";
import { IssueLinks } from "../NotBuilt";

const NOT_BUILT: { label: string; issues: number[] }[] = [
  { label: "Dataset", issues: [160] },
  { label: "Phase", issues: [160] },
  { label: "Repository", issues: [160] },
  // TODO: governance flags have no single issue yet; the review gate and the personal-data
  // pause are the nearest.
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
            {actingFor.name} (
            {actingFor.assurance === "asserted"
              ? "asserted by the operator, not authenticated"
              : actingFor.assurance}
            )
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
