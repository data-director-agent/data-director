/** A list of records: one numbered group of fields per record, with buttons to add and remove. */

import {
  type FieldPlan,
  type Row,
  type ScalarField,
  emptyRow,
  inputId,
  singular,
} from "../../../run/form";
import { Plus, Trash2 } from "lucide-react";
import { Button } from "../../ui/Button";
import { ScalarInput } from "./ScalarInput";

export function RecordsField({
  field,
  prefix,
  rows,
  errorFor,
  onChange,
}: {
  field: Extract<FieldPlan, { fields: ScalarField[] }>;
  prefix: string;
  rows: Row[];
  errorFor: (target: string) => string | undefined;
  onChange: (rows: Row[]) => void;
}) {
  const noun = singular(field.label);
  const setRow = (index: number, row: Row) =>
    onChange(rows.map((r, i) => (i === index ? row : r)));
  return (
    <fieldset className="records">
      <legend>
        {field.label} ({rows.length})
      </legend>
      {field.description && <p className="hint">{field.description}</p>}
      {rows.length === 0 && <p className="muted">None yet.</p>}
      <ol className="record-list">
        {rows.map((row, i) => (
          <li key={i}>
            <fieldset className="record">
              <legend>
                {noun} {i + 1}
              </legend>
              <div className="record-fields">
                {field.fields.map((f) => {
                  const subId = inputId(prefix, field.name, i, f.name);
                  return (
                    <ScalarInput
                      key={f.name}
                      field={f}
                      id={subId}
                      label={f.label}
                      value={row[f.name]}
                      error={errorFor(subId)}
                      onChange={(v) => setRow(i, { ...row, [f.name]: v })}
                    />
                  );
                })}
              </div>
              <Button
                variant="danger"
                size="small"
                icon={Trash2}
                onPress={() => onChange(rows.filter((_, j) => j !== i))}
              >
                Remove {noun.toLowerCase()} {i + 1}
              </Button>
            </fieldset>
          </li>
        ))}
      </ol>
      <Button
        id={inputId(prefix, field.name, "add")}
        icon={Plus}
        onPress={() => onChange([...rows, emptyRow(field.fields)])}
      >
        Add {noun.toLowerCase()}
      </Button>
    </fieldset>
  );
}
