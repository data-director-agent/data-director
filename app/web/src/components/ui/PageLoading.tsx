/**
 * A page that is drawn whole once what it reads on load has landed: until `ready`, one line saying
 * what is being read, as tall as the window so that the footer is already below it. Nothing then
 * arrives above a button after it can be pressed, so nothing moves under the pointer (#1328).
 */

import type { ReactNode } from "react";

export function PageLoading({
  ready,
  said,
  children,
}: {
  ready: boolean;
  /** What is being read, as a status, such as "Reading the project…". */
  said: string;
  children: ReactNode;
}) {
  if (ready) return children;
  return (
    <p role="status" className="page-loading">
      {said}
    </p>
  );
}
