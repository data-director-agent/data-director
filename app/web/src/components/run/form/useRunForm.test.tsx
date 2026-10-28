import { act, renderHook } from "@testing-library/react";
import type { FormEvent } from "react";

import type { JsonSchema } from "../../../run/schema";
import { useRunForm } from "./useRunForm";

const SCHEMA: JsonSchema = {
  type: "object",
  required: ["title"],
  properties: {
    title: { type: "string" },
    count: { type: "integer" },
    parts: {
      type: "array",
      items: { type: "object", required: ["name"], properties: { name: { type: "string" } } },
    },
  },
};

/** A class the form cannot edit: a nested object. */
const UNSUPPORTED: JsonSchema = {
  type: "object",
  properties: { nested: { type: "object", properties: { a: { type: "string" } } } },
};

const submitEvent = { preventDefault: () => undefined } as unknown as FormEvent;

function setup(schema: JsonSchema = SCHEMA) {
  const onRun = vi.fn();
  const hook = renderHook(() => useRunForm("Thing", schema, "run", onRun));
  return { onRun, ...hook };
}

describe("useRunForm in JSON mode", () => {
  it("refuses text that is not JSON, and does not run", () => {
    const { result, onRun } = setup(UNSUPPORTED);
    act(() => result.current.setJson("{nope"));
    act(() => result.current.submit(submitEvent));
    expect(onRun).not.toHaveBeenCalled();
    expect(result.current.errorFor(result.current.jsonId)).toMatch(/not valid JSON/);
  });

  it("refuses JSON that is not an object", () => {
    const { result, onRun } = setup(UNSUPPORTED);
    act(() => result.current.setJson("[1, 2]"));
    act(() => result.current.submit(submitEvent));
    expect(onRun).not.toHaveBeenCalled();
    expect(result.current.errorFor(result.current.jsonId)).toBe("The input must be a JSON object");
  });

  it("runs with the parsed object", () => {
    const { result, onRun } = setup(UNSUPPORTED);
    act(() => result.current.setJson('{"schema_class": "Thing", "x": 1}'));
    act(() => result.current.submit(submitEvent));
    expect(onRun).toHaveBeenCalledWith({ schema_class: "Thing", x: 1 });
    expect(result.current.errors).toEqual([]);
  });

  it("starts in JSON mode and cannot switch when the class has no form", () => {
    const { result } = setup(UNSUPPORTED);
    expect(result.current.plan).toBeNull();
    expect(result.current.asJson).toBe(true);
    act(() => result.current.switchMode());
    expect(result.current.asJson).toBe(true);
  });
});

describe("useRunForm in form mode", () => {
  it("blocks a run with a missing required field", () => {
    const { result, onRun } = setup();
    expect(result.current.asJson).toBe(false);
    act(() => result.current.submit(submitEvent));
    expect(onRun).not.toHaveBeenCalled();
    expect(result.current.errorFor("run-title")).toBe("Enter title");
  });

  it("runs with the document, naming its class", () => {
    const { result, onRun } = setup();
    act(() => result.current.setField("title", "A title"));
    act(() => result.current.setField("count", "3"));
    act(() => result.current.submit(submitEvent));
    expect(onRun).toHaveBeenCalledWith({ schema_class: "Thing", title: "A title", count: 3 });
  });

  it("carries the input to JSON and back", () => {
    const { result } = setup();
    act(() => result.current.setField("title", "A title"));
    act(() => result.current.setField("parts", [{ name: "one" }]));
    act(() => result.current.switchMode());
    expect(result.current.asJson).toBe(true);
    expect(JSON.parse(result.current.json)).toEqual({
      schema_class: "Thing",
      title: "A title",
      parts: [{ name: "one" }],
    });
    act(() => result.current.setJson('{"title": "Edited"}'));
    act(() => result.current.switchMode());
    expect(result.current.asJson).toBe(false);
    expect(result.current.state.title).toBe("Edited");
  });

  it("stays in JSON mode, keeping the text, when it cannot be read back", () => {
    const { result } = setup();
    act(() => result.current.switchMode());
    act(() => result.current.setJson("{nope"));
    act(() => result.current.switchMode());
    expect(result.current.asJson).toBe(true);
    expect(result.current.json).toBe("{nope");
    expect(result.current.errors).toHaveLength(1);
  });

  it("loads an example into the JSON and the fields, clearing errors", () => {
    const { result } = setup();
    act(() => result.current.submit(submitEvent));
    expect(result.current.errors).toHaveLength(1);
    act(() =>
      result.current.load({ name: "e", schema_class: "Thing", input: { title: "From example" } }),
    );
    expect(result.current.errors).toEqual([]);
    expect(result.current.state.title).toBe("From example");
    expect(JSON.parse(result.current.json)).toEqual({ title: "From example" });
  });
});
