/**
 * A part of the shell that is not built yet, drawn in its place so the whole journey is visible
 * (#75). It names the issues that will build it and shows nothing it would show, so no invented
 * data stands in for it.
 */

import type { ReactNode } from "react";

export const ISSUES = "https://github.com/data-director-agent/data-director/issues/";

export function IssueLinks({ issues }: { issues: number[] }) {
  return (
    <>
      {issues.map((n, i) => (
        <span key={n}>
          {i > 0 && ", "}
          <a href={`${ISSUES}${n}`}>#{n}</a>
        </span>
      ))}
    </>
  );
}

export function NotBuilt({
  title,
  issues,
  children,
}: {
  title: string;
  issues: number[];
  children?: ReactNode;
}) {
  return (
    <div className="callout not-built">
      <p>
        <span className="status status-undeclared">Not built yet</span> <strong>{title}</strong>{" "}
        (<IssueLinks issues={issues} />)
      </p>
      {children}
    </div>
  );
}
