/** The errors found on submitting, each linking to its field; it takes focus when shown. */

import type { Ref } from "react";

import type { FieldError } from "../../../run/form";

export function ErrorSummary({
  errors,
  prefix,
  summaryRef,
}: {
  errors: FieldError[];
  prefix: string;
  summaryRef: Ref<HTMLDivElement>;
}) {
  return (
    <div
      className="callout status-danger error-summary"
      role="alert"
      tabIndex={-1}
      ref={summaryRef}
      aria-labelledby={`${prefix}-errors`}
    >
      <p id={`${prefix}-errors`}>
        <strong>Check the input</strong>
      </p>
      <ul>
        {errors.map((e) => (
          <li key={e.target + e.message}>
            <a href={`#${e.target}`}>{e.message}</a>
          </li>
        ))}
      </ul>
    </div>
  );
}
