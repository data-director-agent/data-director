/**
 * The top of a page: its one `h1` and, beneath it, what the reader needs before the content
 * (whom the page acts for, or where the work stands). Every page starts with one, so every page
 * starts in the same place. A page can hide the title on screen and keep the `h1` for screen readers.
 */

import type { ReactNode } from "react";

export function PageHeader({
  title,
  titleHidden,
  className,
  children,
}: {
  title: string;
  titleHidden?: boolean | undefined;
  className?: string;
  children?: ReactNode;
}) {
  return (
    <header className={className ? `page-header ${className}` : "page-header"}>
      <h1 className={titleHidden ? "visually-hidden" : undefined}>{title}</h1>
      {children}
    </header>
  );
}
