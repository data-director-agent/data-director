import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import type { ScalarField } from "../../../run/form";
import { ScalarInput } from "./ScalarInput";

function field(over: Partial<ScalarField> & Pick<ScalarField, "shape">): ScalarField {
  return { name: "f", label: "Thing", required: false, multiline: false, ...over };
}

function show(f: ScalarField, value: string | boolean | undefined = "", error?: string) {
  const onChange = vi.fn();
  render(
    <ScalarInput field={f} id="f" label={f.label} value={value} error={error} onChange={onChange} />,
  );
  return onChange;
}

describe("ScalarInput", () => {
  it("draws a boolean as a checkbox", async () => {
    const onChange = show(field({ shape: { kind: "scalar", type: "boolean" } }), false);
    await userEvent.click(screen.getByRole("checkbox", { name: "Thing" }));
    expect(onChange).toHaveBeenCalledWith(true);
  });

  it("draws options as a choice that can be left unanswered", async () => {
    const onChange = show(field({ shape: { kind: "scalar", type: "string", options: ["a", "b"] } }));
    const select = screen.getByRole("combobox", { name: /Thing/ });
    expect(screen.getByRole("option", { name: "Not given" })).toBeInTheDocument();
    await userEvent.selectOptions(select, "b");
    expect(onChange).toHaveBeenCalledWith("b");
  });

  it("draws prose as a text area", () => {
    show(field({ multiline: true, shape: { kind: "scalar", type: "string" } }));
    expect(screen.getByRole("textbox", { name: /Thing/ }).tagName).toBe("TEXTAREA");
  });

  it("draws a number as a text box with a decimal keypad", () => {
    show(field({ shape: { kind: "scalar", type: "number" } }));
    expect(screen.getByRole("textbox", { name: /Thing/ })).toHaveAttribute("inputmode", "decimal");
  });

  it("shows its error and its description", () => {
    show(
      field({ description: "Help text", shape: { kind: "scalar", type: "string" } }),
      "",
      "Enter thing",
    );
    expect(screen.getByText("Enter thing")).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: /Thing/ })).toHaveAccessibleDescription(/Help text/);
  });
});
