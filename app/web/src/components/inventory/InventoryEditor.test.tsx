import { NO_EDITS, type FileInventory, type InventoryFile } from "@data-director/inventory";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { useState } from "react";

import { httpProjectApi, ProjectApiContext, type ProjectApi, type SavedInventory } from "../../project/api";
import { record, redo, startHistory, undo } from "./history";
import { InventoryEditDialog } from "./InventoryEditDialog";
import { InventoryEditor } from "./InventoryEditor";

function file(path: string, overrides: Partial<InventoryFile> = {}): InventoryFile {
  return {
    file_path: path,
    file_size: 100,
    file_sha256: "0".repeat(64),
    file_media_type: "text/csv",
    file_pronom_ids: ["x-fmt/18"],
    file_identified_by: "extension",
    ...overrides,
  };
}

const STORED: FileInventory = {
  schema_class: "FileInventory",
  inventory_tool: "dd-inventory",
  inventory_tool_version: "0.1.0",
  inventory_made_at: "2026-11-01T09:00:00+00:00",
  inventory_files: [
    file("readings.csv", { file_description: "Soil readings by site" }),
    file("old.csv", { file_role: "data" }),
  ],
};

const RESCAN: FileInventory = {
  ...STORED,
  inventory_made_at: "2026-11-09T09:00:00+00:00",
  inventory_files: [file("readings.csv"), file("new.csv")],
};

describe("history", () => {
  it("records only real changes, and undoes and redoes them", () => {
    const start = startHistory();
    const same = record(start, STORED, { kind: "describe", path: "readings.csv", text: "Soil readings by site" });
    expect(same).toBe(start);
    const once = record(start, STORED, { kind: "omit", path: "old.csv" });
    expect(once.past).toEqual([NO_EDITS]);
    expect(undo(once).present).toBe(NO_EDITS);
    expect(redo(undo(once))).toEqual(once);
    expect(undo(start)).toBe(start);
    expect(redo(start)).toBe(start);
  });
});

describe("InventoryEditor", () => {
  function Editor({ rescan = false }: { rescan?: boolean }) {
    const [history, setHistory] = useState(startHistory);
    return (
      <InventoryEditor
        base={rescan ? RESCAN : STORED}
        history={history}
        onHistory={setHistory}
        rescan={
          rescan
            ? {
                diff: { added: ["new.csv"], removed: ["old.csv"], changed: [], unchanged: 1 },
                orphaned: ["old.csv"],
              }
            : undefined
        }
      />
    );
  }

  it("undoes and redoes a change", async () => {
    const { container } = render(<Editor />);
    const undoButton = screen.getByRole("button", { name: "Undo" });
    expect(undoButton).toBeDisabled();
    const include = screen.getByRole("checkbox", { name: "Include old.csv" });
    await userEvent.click(include);
    expect(include).not.toBeChecked();
    await userEvent.click(undoButton);
    expect(include).toBeChecked();
    await userEvent.click(screen.getByRole("button", { name: "Redo" }));
    expect(include).not.toBeChecked();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("says what a new scan changed and what could not be carried over", async () => {
    render(<Editor rescan />);
    const changed = screen.getByRole("region", { name: "What the new scan changed" });
    expect(within(changed).getByText(/1 file is new/)).toBeInTheDocument();
    expect(within(changed).getByText(/leave it out again/)).toBeInTheDocument();
    await userEvent.click(within(changed).getByText(/no longer listed/));
    expect(within(changed).getByText("old.csv")).toBeInTheDocument();
    expect(screen.getByText("New in this scan")).toBeInTheDocument();
  });
});

describe("InventoryEditDialog", () => {
  function renderDialog(api: Partial<ProjectApi>, onSaved = vi.fn()) {
    render(
      <ProjectApiContext.Provider value={{ ...httpProjectApi, ...api }}>
        <InventoryEditDialog projectId="p1" onSaved={onSaved} />
      </ProjectApiContext.Provider>,
    );
    return onSaved;
  }

  const saved: SavedInventory = {
    digest: "d2",
    file_count: 2,
    inventory_made_at: STORED.inventory_made_at,
    added_at: "2026-11-10T10:00:00+00:00",
    revises: "d1",
  };

  it("saves the project's inventory as edited, and only once it changed", async () => {
    const saveInventory = vi.fn<ProjectApi["saveInventory"]>().mockResolvedValue(saved);
    const onSaved = renderDialog({ inventory: () => Promise.resolve(STORED), saveInventory });
    await userEvent.click(screen.getByRole("button", { name: "Edit inventory" }));
    const dialog = await screen.findByRole("dialog", { name: "Edit the project's inventory" });
    const save = await within(dialog).findByRole("button", { name: "Save as the project's inventory" });
    expect(save).toBeDisabled();
    await userEvent.click(within(dialog).getByRole("checkbox", { name: "Include old.csv" }));
    await userEvent.click(save);
    await waitFor(() => expect(onSaved).toHaveBeenCalledWith(saved));
    const sent = saveInventory.mock.calls[0]?.[1] as FileInventory;
    expect(sent.inventory_files?.map((f) => f.file_path)).toEqual(["readings.csv"]);
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("carries what was said onto a new scan", async () => {
    const saveInventory = vi.fn<ProjectApi["saveInventory"]>().mockResolvedValue(saved);
    renderDialog({ inventory: () => Promise.resolve(STORED), saveInventory });
    await userEvent.click(screen.getByRole("button", { name: "Edit inventory" }));
    const dialog = await screen.findByRole("dialog");
    const input = await within(dialog).findByLabelText("Replace with a new scan of the same folder");
    await userEvent.upload(input, new File([JSON.stringify(RESCAN)], "scan.json", { type: "application/json" }));
    expect(await within(dialog).findByRole("region", { name: "What the new scan changed" })).toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole("button", { name: "Save as the project's inventory" }));
    await waitFor(() => expect(saveInventory).toHaveBeenCalled());
    const sent = saveInventory.mock.calls[0]?.[1] as FileInventory;
    expect(sent.inventory_made_at).toBe(RESCAN.inventory_made_at);
    expect(sent.inventory_files?.[0]?.file_description).toBe("Soil readings by site");
  });

  it("says why a new scan or a save was refused, and keeps the edits", async () => {
    const saveInventory = vi.fn<ProjectApi["saveInventory"]>().mockRejectedValue(new Error("the server answered 400"));
    const onSaved = renderDialog({ inventory: () => Promise.resolve(STORED), saveInventory });
    await userEvent.click(screen.getByRole("button", { name: "Edit inventory" }));
    const dialog = await screen.findByRole("dialog");
    const input = await within(dialog).findByLabelText("Replace with a new scan of the same folder");
    await userEvent.upload(input, new File(["{}"], "scan.json", { type: "application/json" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent(/not an inventory/);
    await userEvent.click(within(dialog).getByRole("checkbox", { name: "Include old.csv" }));
    await userEvent.click(within(dialog).getByRole("button", { name: "Save as the project's inventory" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent(/answered 400/);
    expect(onSaved).not.toHaveBeenCalled();
    expect(within(dialog).getByRole("checkbox", { name: "Include old.csv" })).not.toBeChecked();
  });

  it("says so when the project's inventory cannot be read", async () => {
    renderDialog({ inventory: () => Promise.reject(new Error("the server answered 500")) });
    await userEvent.click(screen.getByRole("button", { name: "Edit inventory" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/answered 500/);
  });
});
