/**
 * What a person's decision forms share: the reason they give, and the alert that says the decision
 * was not recorded, which takes focus when it appears.
 */

import { type ReactNode, useEffect, useRef, useState } from "react";

export function useDecisionError() {
  const [error, setError] = useState<string | null>(null);
  const errorRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (error) errorRef.current?.focus();
  }, [error]);

  const alert = error && (
    <div
      role="alert"
      className="callout status-danger"
      ref={errorRef}
      tabIndex={-1}
    >
      <p>The decision was not recorded: {error}</p>
    </div>
  );
  return { setError, alert };
}

export function ReasonField({
  id,
  label,
  hint,
  required = false,
  maxLength,
  rows,
  value,
  onChange,
}: {
  id: string;
  label: string;
  hint: ReactNode;
  required?: boolean;
  maxLength: number;
  rows: number;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <div className="field">
      <label htmlFor={`${id}-reason`}>{label}</label>
      <p className="hint" id={`${id}-reason-hint`}>
        {hint}
      </p>
      <textarea
        id={`${id}-reason`}
        aria-describedby={`${id}-reason-hint`}
        required={required}
        maxLength={maxLength}
        rows={rows}
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
    </div>
  );
}
