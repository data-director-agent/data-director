/** One planned field, drawn by its shape: a value, a list edited one per line, or records. */

import {
  type FieldPlan,
  type FormState,
  type Row,
  type ScalarField,
  inputId,
} from "../../../run/form";
import { Field } from "./Field";
import { RecordsField } from "./RecordsField";
import { ScalarInput } from "./ScalarInput";

export function PlannedField({
  field,
  prefix,
  value,
  errorFor,
  onChange,
}: {
  field: FieldPlan;
  prefix: string;
  value: FormState[string] | undefined;
  errorFor: (target: string) => string | undefined;
  onChange: (value: FormState[string]) => void;
}) {
  const id = inputId(prefix, field.name);
  if (field.shape.kind === "scalar") {
    return (
      <ScalarInput
        field={field as ScalarField}
        id={id}
        label={field.label}
        value={value as string | boolean | undefined}
        error={errorFor(id)}
        onChange={onChange}
      />
    );
  }
  if (field.shape.kind === "list") {
    return (
      <Field
        id={id}
        label={field.label}
        description={[field.description, "One per line."].filter(Boolean).join(" ")}
        error={errorFor(id)}
        required={field.required}
      >
        {(props) => (
          <textarea
            {...props}
            rows={4}
            value={typeof value === "string" ? value : ""}
            onChange={(e) => onChange(e.target.value)}
          />
        )}
      </Field>
    );
  }
  if (!("fields" in field)) return null;
  return (
    <RecordsField
      field={field}
      prefix={prefix}
      rows={(value as Row[] | undefined) ?? []}
      errorFor={errorFor}
      onChange={onChange}
    />
  );
}
