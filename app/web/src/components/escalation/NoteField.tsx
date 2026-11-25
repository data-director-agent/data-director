/**
 * The note that goes with a move on an escalation or a steward's step: a labelled text area, at
 * most as long as the harness keeps (`NOTE_MAX_LENGTH`).
 */

import { useId } from "react";

import { NOTE_MAX_LENGTH } from "../../project/escalations";

export function NoteField({
  label,
  value,
  onChange,
  required = true,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  required?: boolean;
}) {
  const id = useId();
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <textarea
        id={id}
        required={required}
        rows={3}
        maxLength={NOTE_MAX_LENGTH}
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
    </div>
  );
}
