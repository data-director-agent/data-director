/**
 * The run form's model, drawn from the input class's JSON Schema: which fields to ask for, the
 * form's state for a document, and the document for the form's state.
 *
 * It covers the shapes input classes use today: text, numbers, yes/no, a choice from an enum, a
 * list of text (one per line), and a list of records whose fields are all of those. A class
 * with any other shape is edited as JSON. Checks are limited to required fields and numbers;
 * the conductor's input check is the authority (#69 brings full validation).
 */

import { fieldName } from "../manifest/wording";
import { type JsonSchema, type ScalarType, type Shape, properties, shapeOf } from "./schema";

type ScalarShape = Extract<Shape, { kind: "scalar" }>;

export interface ScalarField {
  name: string;
  label: string;
  description?: string;
  required: boolean;
  shape: ScalarShape;
  multiline: boolean;
}

export type FieldPlan =
  | ScalarField
  | (Omit<ScalarField, "shape" | "multiline"> & { shape: { kind: "list"; item: ScalarType } })
  | (Omit<ScalarField, "shape" | "multiline"> & {
      shape: { kind: "records" };
      fields: ScalarField[];
    });

export type Row = Record<string, string | boolean>;
export type FormState = Record<string, string | boolean | Row[]>;

export interface FieldError {
  /** The id of the input the message is about. */
  target: string;
  message: string;
}

/** Shown first, in this order, when a class has them; then text, lists and records. */
const LEADING = ["title", "name", "description"];

/** What every kind of field has: its name, its label, its help and whether it is required. */
function common(name: string, schema: JsonSchema, required: boolean) {
  const base: { name: string; label: string; required: boolean; description?: string } = {
    name,
    label: schema.title && schema.title !== name ? schema.title : fieldName(name),
    required,
  };
  if (schema.description) base.description = schema.description;
  return base;
}

function scalarField(
  name: string,
  schema: JsonSchema,
  shape: ScalarShape,
  required: boolean,
): ScalarField {
  return {
    ...common(name, schema, required),
    shape,
    multiline: shape.type === "string" && !shape.options && /description|abstract/.test(name),
  };
}

function rank(field: FieldPlan): number {
  const leading = LEADING.indexOf(field.name);
  if (leading >= 0) return leading;
  return { scalar: 10, list: 20, records: 30 }[field.shape.kind];
}

/** The fields to ask for, or null if the class has a shape the form cannot edit. */
export function planFields(root: JsonSchema): FieldPlan[] | null {
  const required = new Set(root.required ?? []);
  const plan: FieldPlan[] = [];
  for (const [name, schema] of properties(root)) {
    const shape = shapeOf(root, schema);
    if (shape.kind === "scalar") {
      plan.push(scalarField(name, schema, shape, required.has(name)));
    } else if (shape.kind === "list") {
      plan.push({ ...common(name, schema, required.has(name)), shape });
    } else if (shape.kind === "records") {
      const inner = new Set(shape.schema.required ?? []);
      const fields: ScalarField[] = [];
      for (const [sub, subSchema] of properties(shape.schema)) {
        const subShape = shapeOf(root, subSchema);
        if (subShape.kind !== "scalar") return null;
        fields.push(scalarField(sub, subSchema, subShape, inner.has(sub)));
      }
      plan.push({ ...common(name, schema, required.has(name)), shape: { kind: "records" }, fields });
    } else {
      return null;
    }
  }
  return plan.sort((a, b) => rank(a) - rank(b));
}

function scalarToForm(value: unknown, shape: ScalarShape): string | boolean {
  if (shape.type === "boolean") return value === true;
  return value === undefined || value === null ? "" : String(value);
}

export function toForm(plan: FieldPlan[], document: Record<string, unknown>): FormState {
  const state: FormState = {};
  for (const field of plan) {
    const value = document[field.name];
    if (field.shape.kind === "scalar") {
      state[field.name] = scalarToForm(value, field.shape);
    } else if (field.shape.kind === "list") {
      state[field.name] = Array.isArray(value) ? value.map(String).join("\n") : "";
    } else if ("fields" in field) {
      const rows = Array.isArray(value) ? (value as Record<string, unknown>[]) : [];
      state[field.name] = rows.map((row) =>
        Object.fromEntries(field.fields.map((f) => [f.name, scalarToForm(row[f.name], f.shape)])),
      );
    }
  }
  return state;
}

export function emptyRow(fields: ScalarField[]): Row {
  return Object.fromEntries(fields.map((f) => [f.name, f.shape.type === "boolean" ? false : ""]));
}

function scalarFromForm(value: string | boolean, type: ScalarType): unknown {
  if (type === "boolean") return value === true;
  const text = String(value).trim();
  if (text === "") return undefined;
  if (type === "number" || type === "integer") return Number(text);
  return text;
}

/** The document the form's state stands for. Empty fields are left out, not sent as "". */
export function toDocument(
  plan: FieldPlan[],
  state: FormState,
  schemaClass: string,
): Record<string, unknown> {
  const document: Record<string, unknown> = { schema_class: schemaClass };
  for (const field of plan) {
    const value = state[field.name];
    if (field.shape.kind === "scalar") {
      const converted = scalarFromForm(value as string | boolean, field.shape.type);
      if (converted !== undefined) document[field.name] = converted;
    } else if (field.shape.kind === "list") {
      const { item } = field.shape;
      const lines = String(value ?? "")
        .split("\n")
        .map((line) => scalarFromForm(line, item))
        .filter((v) => v !== undefined);
      if (lines.length > 0) document[field.name] = lines;
    } else if ("fields" in field) {
      const rows = ((value as Row[] | undefined) ?? [])
        .map((row) => {
          const out: Record<string, unknown> = {};
          for (const f of field.fields) {
            const converted = scalarFromForm(row[f.name] ?? "", f.shape.type);
            if (converted !== undefined) out[f.name] = converted;
          }
          return out;
        })
        .filter((row) => Object.keys(row).length > 0);
      if (rows.length > 0) document[field.name] = rows;
    }
  }
  return document;
}

export function inputId(prefix: string, ...path: (string | number)[]): string {
  return [prefix, ...path].join("-");
}

function scalarError(
  field: ScalarField,
  value: string | boolean | undefined,
  target: string,
  label: string,
): FieldError | null {
  if (field.shape.type === "boolean") return null;
  const text = String(value ?? "").trim();
  if (text === "") return field.required ? { target, message: `Enter ${label}` } : null;
  if (field.shape.type === "number" && Number.isNaN(Number(text))) {
    return { target, message: `${label} must be a number` };
  }
  if (field.shape.type === "integer" && !Number.isInteger(Number(text))) {
    return { target, message: `${label} must be a whole number` };
  }
  return null;
}

export function check(plan: FieldPlan[], state: FormState, prefix: string): FieldError[] {
  const errors: FieldError[] = [];
  for (const field of plan) {
    const value = state[field.name];
    if (field.shape.kind === "scalar") {
      const error = scalarError(
        field as ScalarField,
        value as string | boolean,
        inputId(prefix, field.name),
        field.label.toLowerCase(),
      );
      if (error) errors.push(error);
    } else if (field.shape.kind === "list") {
      if (field.required && String(value ?? "").trim() === "") {
        errors.push({ target: inputId(prefix, field.name), message: `Enter ${field.label}` });
      }
    } else if ("fields" in field) {
      const rows = (value as Row[] | undefined) ?? [];
      if (field.required && rows.length === 0) {
        errors.push({ target: inputId(prefix, field.name, "add"), message: `Add ${field.label}` });
      }
      rows.forEach((row, i) => {
        for (const f of field.fields) {
          const error = scalarError(
            f,
            row[f.name],
            inputId(prefix, field.name, i, f.name),
            `${f.label.toLowerCase()} of ${singular(field.label).toLowerCase()} ${i + 1}`,
          );
          if (error) errors.push(error);
        }
      });
    }
  }
  return errors;
}

/** "Fields" → "Field": a label for one record of a list. */
export function singular(label: string): string {
  return label.endsWith("s") && !label.endsWith("ss") ? label.slice(0, -1) : label;
}
