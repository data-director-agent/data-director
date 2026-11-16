/**
 * A wide table that scrolls within its own region rather than the page (WCAG 1.4.10 exempts data
 * tables). The region is named and takes focus, so it can be found by a screen reader and scrolled
 * from the keyboard.
 */

import type { ReactNode } from "react";

export function TableScroll({
  label,
  className,
  children,
}: {
  label: string;
  className?: string;
  children: ReactNode;
}) {
  return (
    <div
      className={className ? `table-scroll ${className}` : "table-scroll"}
      role="region"
      aria-label={label}
      // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex
      tabIndex={0}
    >
      {children}
    </div>
  );
}
