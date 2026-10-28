/**
 * The run form: the agent's input class, drawn from its JSON Schema (run/form.ts), with example
 * inputs to start from and a JSON editor for anything the form cannot draw.
 *
 * Errors are listed in a summary that takes focus and links to each field, and each field
 * names its own error. The form checks only required fields and numbers; the conductor's input
 * check decides (#69 brings full validation). The state lives in `form/useRunForm.ts` and the
 * fields are drawn by the components beside it.
 */

import "./RunForm.css";

import { type Ref, useId } from "react";

import { Braces, FileInput, ListChecks, Play } from "lucide-react";
import { className, fieldName } from "../../manifest/wording";
import type { JsonSchema } from "../../run/schema";
import type { Example } from "../../run/types";
import { Button } from "../ui/Button";
import { ErrorSummary } from "./form/ErrorSummary";
import { Field } from "./form/Field";
import { PlannedField } from "./form/PlannedField";
import { useRunForm } from "./form/useRunForm";

export interface RunFormProps {
  schemaClass: string;
  schema: JsonSchema;
  examples: Example[];
  running: boolean;
  onRun: (input: Record<string, unknown>) => void;
  headingRef?: Ref<HTMLHeadingElement>;
}

export function RunForm({ schemaClass, schema, examples, running, onRun, headingRef }: RunFormProps) {
  const prefix = useId().replace(/:/g, "");
  const form = useRunForm(schemaClass, schema, prefix, onRun);
  const { plan, jsonId } = form;
  const headingId = `${prefix}-heading`;
  const fitting = examples.filter((e) => e.schema_class === schemaClass);

  return (
    <form className="run-form" aria-labelledby={headingId} onSubmit={form.submit} noValidate>
      <h3 id={headingId} ref={headingRef} tabIndex={-1}>
        Input: {className(schemaClass)}
      </h3>

      {form.errors.length > 0 && (
        <ErrorSummary errors={form.errors} prefix={prefix} summaryRef={form.summaryRef} />
      )}

      <div className="form-tools">
        {fitting.length > 0 && (
          <div className="example-buttons" role="group" aria-label="Examples">
            {fitting.map((e) => (
              <Button key={e.name} size="small" icon={FileInput} onPress={() => form.load(e)}>
                Load example: {fieldName(e.name).toLowerCase()}
              </Button>
            ))}
          </div>
        )}
        {plan && (
          <Button
            size="small"
            variant="quiet"
            icon={form.asJson ? ListChecks : Braces}
            onPress={form.switchMode}
          >
            {form.asJson ? "Edit as a form" : "Edit as JSON"}
          </Button>
        )}
      </div>

      {!plan && (
        <p className="muted">
          This input has a shape the form cannot draw yet, so it is edited as JSON.
        </p>
      )}

      {form.asJson || !plan ? (
        <Field id={jsonId} label="Input as JSON" error={form.errorFor(jsonId)}>
          {(props) => (
            <textarea
              {...props}
              className="json-input"
              rows={16}
              spellCheck={false}
              value={form.json}
              onChange={(e) => form.setJson(e.target.value)}
            />
          )}
        </Field>
      ) : (
        plan.map((field) => (
          <PlannedField
            key={field.name}
            field={field}
            prefix={prefix}
            value={form.state[field.name]}
            errorFor={form.errorFor}
            onChange={(value) => form.setField(field.name, value)}
          />
        ))
      )}

      <div className="form-actions">
        <Button type="submit" variant="primary" icon={Play} isPending={running}>
          {running ? "Running…" : "Run"}
        </Button>
      </div>
    </form>
  );
}
