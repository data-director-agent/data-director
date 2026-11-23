/**
 * The inputs a project fact's values are set with: a line of text, or a few sentences, and a
 * choice from fixed options (`FactFields`, `ProjectFactValues`).
 */

import { useId } from "react";

import type { ProjectFact } from "../../project/facts";

export type Setter = (
  slot: keyof ProjectFact,
  value: string | string[] | undefined,
) => void;

export function TextValue({
  label,
  hint,
  slot,
  fact,
  set,
  required = false,
  long = false,
}: {
  label: string;
  hint?: string;
  slot: keyof ProjectFact;
  fact: ProjectFact;
  set: Setter;
  required?: boolean;
  /** A few sentences in a person's own words, rather than a name or an identifier. */
  long?: boolean;
}) {
  const id = useId();
  const value = fact[slot];
  return (
    <div className="field">
      <label htmlFor={id}>
        {label} {required ? "(required)" : "(optional)"}
      </label>
      {hint && (
        <p className="hint" id={`${id}-hint`}>
          {hint}
        </p>
      )}
      {long ? (
        <textarea
          id={id}
          rows={3}
          required={required}
          aria-describedby={hint ? `${id}-hint` : undefined}
          value={typeof value === "string" ? value : ""}
          onChange={(event) => set(slot, event.target.value)}
        />
      ) : (
        <input
          id={id}
          type="text"
          required={required}
          aria-describedby={hint ? `${id}-hint` : undefined}
          value={Array.isArray(value) ? value.join(", ") : (value ?? "")}
          onChange={(event) => set(slot, event.target.value)}
        />
      )}
    </div>
  );
}

export function Choice<T extends string>({
  label,
  slot,
  options,
  labels,
  fact,
  set,
  optional = false,
}: {
  label: string;
  slot: keyof ProjectFact;
  options: readonly T[];
  labels: Record<T, string>;
  fact: ProjectFact;
  set: Setter;
  optional?: boolean;
}) {
  const id = useId();
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <select
        id={id}
        value={(fact[slot] as string | undefined) ?? ""}
        onChange={(event) => set(slot, event.target.value || undefined)}
      >
        {optional && <option value="">Not said</option>}
        {options.map((option) => (
          <option key={option} value={option}>
            {labels[option]}
          </option>
        ))}
      </select>
    </div>
  );
}
