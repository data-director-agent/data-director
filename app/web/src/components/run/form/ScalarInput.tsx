/** One value: a checkbox, a choice of options, a text area for prose or a text box. */

import type { ScalarField } from "../../../run/form";
import { Field } from "./Field";

export function ScalarInput({
  field,
  id,
  label,
  value,
  error,
  onChange,
}: {
  field: ScalarField;
  id: string;
  label: string;
  value: string | boolean | undefined;
  error: string | undefined;
  onChange: (value: string | boolean) => void;
}) {
  if (field.shape.type === "boolean") {
    return (
      <div className="field field-check">
        <input
          id={id}
          type="checkbox"
          checked={value === true}
          onChange={(e) => onChange(e.target.checked)}
        />
        <label htmlFor={id}>{label}</label>
      </div>
    );
  }
  const text = typeof value === "string" ? value : "";
  const { options } = field.shape;
  return (
    <Field
      id={id}
      label={label}
      description={field.description}
      error={error}
      required={field.required}
    >
      {(props) =>
        options ? (
          <select {...props} value={text} onChange={(e) => onChange(e.target.value)}>
            <option value="">Not given</option>
            {options.map((o) => (
              <option key={o} value={o}>
                {o}
              </option>
            ))}
          </select>
        ) : field.multiline ? (
          <textarea {...props} rows={4} value={text} onChange={(e) => onChange(e.target.value)} />
        ) : (
          <input
            {...props}
            type="text"
            inputMode={field.shape.type === "string" ? undefined : "decimal"}
            value={text}
            onChange={(e) => onChange(e.target.value)}
          />
        )
      }
    </Field>
  );
}
