/**
 * A labelled field with its hint and error. The input itself is drawn by the caller, which is
 * given the id and ARIA attributes that tie it to the label, hint and error.
 */

import type { ReactNode } from "react";

export interface InputProps {
  id: string;
  "aria-describedby"?: string;
  "aria-invalid"?: true;
}

export function Field({
  id,
  label,
  description,
  error,
  required,
  children,
}: {
  id: string;
  label: string;
  description?: string | undefined;
  error?: string | undefined;
  required?: boolean;
  children: (props: InputProps) => ReactNode;
}) {
  const described = [description && `${id}-hint`, error && `${id}-error`].filter(Boolean);
  const props: InputProps = { id };
  if (described.length > 0) props["aria-describedby"] = described.join(" ");
  if (error) props["aria-invalid"] = true;
  return (
    <div className={error ? "field field-invalid" : "field"}>
      <label htmlFor={id}>
        {label}
        {required && <span className="muted"> (required)</span>}
      </label>
      {description && (
        <p id={`${id}-hint`} className="hint">
          {description}
        </p>
      )}
      {error && (
        <p id={`${id}-error`} className="field-error">
          <span className="status status-danger">Error</span> {error}
        </p>
      )}
      {children(props)}
    </div>
  );
}
