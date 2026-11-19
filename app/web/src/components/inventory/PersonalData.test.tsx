import type { FileInventory, InventoryFile, PersonalDataFinding } from "@data-director/inventory";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";

import { InventoryView } from "./InventoryView";

function file(path: string, overrides: Partial<InventoryFile> = {}): InventoryFile {
  return {
    file_path: path,
    file_size: 1500,
    file_sha256: path.length.toString(16).padStart(64, "0"),
    file_identified_by: "extension",
    file_description: "Described",
    ...overrides,
  };
}

function finding(overrides: Partial<PersonalDataFinding>): PersonalDataFinding {
  return {
    finding_kind: "email address",
    finding_file: "people/participants.csv",
    finding_target: "column",
    finding_column: "contact",
    finding_proportion: "over 50%",
    finding_confidence: "high",
    finding_detector: "presidio-analyzer 2.2.366",
    finding_examined: 200,
    ...overrides,
  };
}

const UNCHECKED: FileInventory = {
  schema_class: "FileInventory",
  inventory_files: [
    file("people/participants.csv", { file_fields: [{ name: "contact" }, { name: "telephone" }] }),
    file("data/readings.csv", { file_fields: [{ name: "ph" }] }),
  ],
  inventory_tool: "dd-inventory",
  inventory_tool_version: "0.1.0",
  inventory_made_at: "2026-11-18T09:00:00+00:00",
};

const CHECKED: FileInventory = {
  ...UNCHECKED,
  inventory_personal_data: [
    finding({}),
    finding({ finding_kind: "phone number", finding_column: "telephone", finding_confidence: "medium" }),
  ],
};

function section(): HTMLElement {
  return screen.getByRole("region", { name: "Possible personal data" });
}

describe("InventoryView, personal data", () => {
  it("lists where possible personal data was found, by file, without any value", async () => {
    const { container } = render(<InventoryView inventory={CHECKED} />);
    const found = within(section()).getByRole("list", {
      name: "Possible personal data in people/participants.csv",
    });
    expect(within(found).getAllByRole("listitem")).toHaveLength(2);
    expect(found).toHaveTextContent("contact");
    expect(section()).not.toHaveTextContent("presidio");
    expect(await axe(container)).toHaveNoViolations();
  });

  it("marks a file with findings, and counts it in its closed folder", async () => {
    render(<InventoryView inventory={CHECKED} />);
    expect(screen.getByText("people/").closest("summary")).toHaveTextContent("1 file to look at");
    expect(screen.getByText("data/").closest("summary")).not.toHaveTextContent("to look at");
    await userEvent.click(screen.getByText("people/"));
    const files = screen.getByRole("region", { name: "Files" });
    expect(within(files).getByText("Possible personal data")).toBeInTheDocument();
    expect(within(files).getByText(/^1 file marked to look at/)).toBeInTheDocument();
  });

  it("tells an inventory with nothing found from one never checked", () => {
    const { rerender } = render(<InventoryView inventory={{ ...UNCHECKED, inventory_personal_data: [] }} />);
    const nothing = section().textContent;
    expect(within(section()).queryByRole("list")).toBeNull();
    rerender(<InventoryView inventory={UNCHECKED} />);
    expect(section().textContent).not.toBe(nothing);
    expect(within(section()).queryByRole("list")).toBeNull();
    expect(screen.queryByText("Possible personal data", { selector: ".status" })).toBeNull();
  });
});
