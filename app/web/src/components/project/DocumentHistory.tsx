/**
 * Every version of a document, newest first: who added it and when, what was decided on it and
 * why, a link that opens it in the reader, and what it changed from the version before.
 */

import type { DocumentVersion, ProjectDocument } from "../../project/api";
import { Link } from "../../route";
import { Provenance, State } from "./DocumentFacts";
import { VersionDiff } from "./VersionDiff";

export function DocumentHistory({
  document,
  shown,
  hrefFor,
}: {
  document: ProjectDocument;
  /** The version the reader shows. */
  shown: number;
  hrefFor: (version: DocumentVersion) => string;
}) {
  const versions = document.versions;
  return (
    <ol reversed className="plain-list document-history">
      {[...versions].reverse().map((version) => {
        const before = versions.find((v) => v.version === version.version - 1);
        const current = version.version === shown;
        return (
          <li key={version.version} className="document-history-entry">
            <p className="document-history-title">
              {current ? (
                <strong aria-current="true">Version {version.version} (shown)</strong>
              ) : (
                <Link to={hrefFor(version)}>Version {version.version}</Link>
              )}{" "}
              <State version={version} />
            </p>
            <p className="hint">
              <Provenance version={version} />.
            </p>
            {version.decision?.reason && (
              <p>
                <strong>Reason:</strong> {version.decision.reason}
              </p>
            )}
            {before && (
              <details className="document-changes">
                <summary>Changes from version {before.version}</summary>
                <VersionDiff before={before.text} after={version.text} />
              </details>
            )}
          </li>
        );
      })}
    </ol>
  );
}
