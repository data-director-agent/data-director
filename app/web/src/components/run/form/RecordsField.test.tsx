import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";

import type { FieldPlan, Row, ScalarField } from "../../../run/form";
import { RecordsField } from "./RecordsField";

const NAME: ScalarField = {
  name: "name",
  label: "Name",
  required: true,
  shape: { kind: "scalar", type: "string" },
  multiline: false,
};
const FIELD = {
  name: "parts",
  label: "Parts",
  required: false,
  shape: { kind: "records" },
  fields: [NAME],
} as Extract<FieldPlan, { fields: ScalarField[] }>;

function Harness({ initial }: { initial: Row[] }) {
  const [rows, setRows] = useState(initial);
  return (
    <RecordsField
      field={FIELD}
      prefix="run"
      rows={rows}
      errorFor={() => undefined}
      onChange={setRows}
    />
  );
}

describe("RecordsField", () => {
  it("says when there are none and adds a record", async () => {
    const user = userEvent.setup();
    render(<Harness initial={[]} />);
    expect(screen.getByText("None yet.")).toBeInTheDocument();
    expect(screen.getByText("Parts (0)")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Add part" }));
    expect(screen.getByText("Parts (1)")).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "Part 1" })).toBeInTheDocument();
  });

  it("edits one record without touching the others", async () => {
    const user = userEvent.setup();
    render(<Harness initial={[{ name: "a" }, { name: "b" }]} />);
    const [first, second] = screen.getAllByLabelText(/^Name/);
    await user.type(first as HTMLElement, "x");
    expect(first).toHaveValue("ax");
    expect(second).toHaveValue("b");
  });

  it("removes a record from the middle and renumbers the rest", async () => {
    const user = userEvent.setup();
    render(<Harness initial={[{ name: "a" }, { name: "b" }, { name: "c" }]} />);
    await user.click(screen.getByRole("button", { name: "Remove part 2" }));
    const names = screen.getAllByLabelText(/^Name/).map((el) => (el as HTMLInputElement).value);
    expect(names).toEqual(["a", "c"]);
    expect(screen.getByRole("group", { name: "Part 2" })).toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "Part 3" })).not.toBeInTheDocument();
  });
});
