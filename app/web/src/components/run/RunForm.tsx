/**
 * The run form: the agent's input class, drawn from its JSON Schema (run/form.ts), with example
 * inputs to start from and a JSON editor for anything the form cannot draw.
 *
 * Errors are listed in a summary that takes focus and links to each field, and each field
 * names its own error. The form checks only required fields and numbers; the conductor's input
 * check decides (#69 brings full validation).
 */

import {
  type FormEvent,
  type ReactNode,
  type Ref,
  useId,
  useMemo,
  useRef,
  useState,
} from "react";

import { className, fieldName } from "../../manifest/wording";
import {
  type FieldError,
  type FieldPlan,
  type FormState,
  type Row,
  type ScalarField,
  check,
  emptyRow,
  inputId,
  planFields,
  singular,
  toDocument,
  toForm,
} from "../../run/form";
import type { JsonSchema } from "../../run/schema";
import type { Example } from "../../run/types";

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
  const plan = useMemo(() => planFields(schema), [schema]);
  const [state, setState] = useState<FormState>(() => (plan ? toForm(plan, {}) : {}));
  const [asJson, setAsJson] = useState(plan === null);
  const [json, setJson] = useState(() => JSON.stringify({ schema_class: schemaClass }, null, 2));
  const [errors, setErrors] = useState<FieldError[]>([]);
  const summaryRef = useRef<HTMLDivElement>(null);
  const headingId = `${prefix}-heading`;
  const jsonId = inputId(prefix, "json");

  function show(found: FieldError[]) {
    setErrors(found);
    if (found.length > 0) queueMicrotask(() => summaryRef.current?.focus());
  }

  function load(example: Example) {
    setErrors([]);
    setJson(JSON.stringify(example.input, null, 2));
    if (plan) setState(toForm(plan, example.input));
  }

  function parseJson(): Record<string, unknown> | null {
    try {
      const parsed: unknown = JSON.parse(json);
      if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
        return parsed as Record<string, unknown>;
      }
      show([{ target: jsonId, message: "The input must be a JSON object" }]);
    } catch (error) {
      show([{ target: jsonId, message: `The input is not valid JSON: ${String(error)}` }]);
    }
    return null;
  }

  function switchMode() {
    if (!plan) return;
    if (asJson) {
      const parsed = parseJson();
      if (!parsed) return;
      setState(toForm(plan, parsed));
    } else {
      setJson(JSON.stringify(toDocument(plan, state, schemaClass), null, 2));
    }
    setErrors([]);
    setAsJson(!asJson);
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    if (asJson || !plan) {
      const parsed = parseJson();
      if (parsed) {
        setErrors([]);
        onRun(parsed);
      }
      return;
    }
    const found = check(plan, state, prefix);
    show(found);
    if (found.length === 0) onRun(toDocument(plan, state, schemaClass));
  }

  const errorFor = (target: string) => errors.find((e) => e.target === target)?.message;
  const fitting = examples.filter((e) => e.schema_class === schemaClass);

  return (
    <form className="run-form" aria-labelledby={headingId} onSubmit={submit} noValidate>
      <h3 id={headingId} ref={headingRef} tabIndex={-1}>
        Input: {className(schemaClass)}
      </h3>

      {errors.length > 0 && (
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
      )}

      <div className="form-tools">
        {fitting.length > 0 && (
          <div className="example-buttons" role="group" aria-label="Examples">
            {fitting.map((e) => (
              <button key={e.name} type="button" onClick={() => load(e)}>
                Load example: {fieldName(e.name).toLowerCase()}
              </button>
            ))}
          </div>
        )}
        {plan && (
          <button type="button" onClick={switchMode}>
            {asJson ? "Edit as a form" : "Edit as JSON"}
          </button>
        )}
      </div>

      {!plan && (
        <p className="muted">
          This input has a shape the form cannot draw yet, so it is edited as JSON.
        </p>
      )}

      {asJson || !plan ? (
        <Field id={jsonId} label="Input as JSON" error={errorFor(jsonId)}>
          {(props) => (
            <textarea
              {...props}
              className="json-input"
              rows={16}
              spellCheck={false}
              value={json}
              onChange={(e) => setJson(e.target.value)}
            />
          )}
        </Field>
      ) : (
        plan.map((field) => (
          <PlannedField
            key={field.name}
            field={field}
            prefix={prefix}
            value={state[field.name]}
            errorFor={errorFor}
            onChange={(value) => setState((s) => ({ ...s, [field.name]: value }))}
          />
        ))
      )}

      <div className="form-actions">
        <button type="submit" className="primary" aria-disabled={running || undefined}>
          {running ? "Running…" : "Run"}
        </button>
      </div>
    </form>
  );
}

interface InputProps {
  id: string;
  "aria-describedby"?: string;
  "aria-invalid"?: true;
}

function Field({
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

function ScalarInput({
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

function PlannedField({
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
  const rows = (value as Row[] | undefined) ?? [];
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
              <button type="button" onClick={() => onChange(rows.filter((_, j) => j !== i))}>
                Remove {noun.toLowerCase()} {i + 1}
              </button>
            </fieldset>
          </li>
        ))}
      </ol>
      <button
        type="button"
        id={inputId(prefix, field.name, "add")}
        onClick={() => onChange([...rows, emptyRow(field.fields)])}
      >
        Add {noun.toLowerCase()}
      </button>
    </fieldset>
  );
}
