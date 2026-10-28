/**
 * The run form's state: the planned fields or the JSON text, whichever is being edited, and the
 * errors found on submitting. Switching between the two carries the input across.
 */

import { type FormEvent, useMemo, useRef, useState } from "react";

import {
  type FieldError,
  type FormState,
  check,
  inputId,
  planFields,
  toDocument,
  toForm,
} from "../../../run/form";
import type { JsonSchema } from "../../../run/schema";
import type { Example } from "../../../run/types";

export function useRunForm(
  schemaClass: string,
  schema: JsonSchema,
  prefix: string,
  onRun: (input: Record<string, unknown>) => void,
) {
  const plan = useMemo(() => planFields(schema), [schema]);
  const [state, setState] = useState<FormState>(() => (plan ? toForm(plan, {}) : {}));
  const [asJson, setAsJson] = useState(plan === null);
  const [json, setJson] = useState(() => JSON.stringify({ schema_class: schemaClass }, null, 2));
  const [errors, setErrors] = useState<FieldError[]>([]);
  const summaryRef = useRef<HTMLDivElement>(null);
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

  function setField(name: string, value: FormState[string]) {
    setState((s) => ({ ...s, [name]: value }));
  }

  const errorFor = (target: string) => errors.find((e) => e.target === target)?.message;

  return {
    plan,
    state,
    setField,
    asJson,
    json,
    setJson,
    jsonId,
    errors,
    errorFor,
    summaryRef,
    load,
    switchMode,
    submit,
  };
}
