/**
 * Whom this work acts for and whose rules apply. Where the project itself stands (its dataset,
 * phase, repository and governance flags) is in the project overview beside the conversation
 * (`ContextPanel`).
 *
 * The principal is the signed-in person, with who vouched for them, or on a development server
 * the operator's assertion, and the bar says which (docs/specs/policy-and-identity.md).
 */

import "./StatusBar.css";

import type { Directory } from "../../manifest/normalise";
import { Link } from "../../route";
import { assuranceText } from "../../session/api";

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
            <Link to="/policy">
              <code>{profileRef}</code>
            </Link>
          </dd>
        </div>
      </dl>
    </section>
  );
}
