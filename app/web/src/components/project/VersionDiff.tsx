/**
 * The lines one version changed from the one before, one line each, marked with a sign as well
 * as a colour (`docs/ui/best-practices.md`, 7), and as `<ins>` and `<del>` for a screen reader.
 */

import { diffLines } from "../../project/diff";

export function VersionDiff({ before, after }: { before: string; after: string }) {
  const changes = diffLines(before, after);
  const added = changes.filter((change) => change.kind === "added").length;
  const removed = changes.filter((change) => change.kind === "removed").length;
  if (added + removed === 0) return <p className="hint">The text is the same.</p>;
  return (
    <>
      <p className="hint">
        {added} {added === 1 ? "line" : "lines"} added, {removed} {removed === 1 ? "line" : "lines"}{" "}
        removed.
      </p>
      <pre className="version-diff">
        {changes.map((change, i) => {
          if (change.kind === "added") {
            return (
              <ins key={i} className="diff-line diff-added">
                <span aria-hidden="true">+ </span>
                {change.text}
                {"\n"}
              </ins>
            );
          }
          if (change.kind === "removed") {
            return (
              <del key={i} className="diff-line diff-removed">
                <span aria-hidden="true">− </span>
                {change.text}
                {"\n"}
              </del>
            );
          }
          return (
            <span key={i} className="diff-line">
              <span aria-hidden="true">{"  "}</span>
              {change.text}
              {"\n"}
            </span>
          );
        })}
      </pre>
    </>
  );
}
