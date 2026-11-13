import type { FileInventory } from "@data-director/inventory";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { httpProjectApi, ProjectApiContext, type ProjectApi, type SavedInventory } from "../../project/api";
import { AddInventory } from "./AddInventory";

const INVENTORY: FileInventory = {
  schema_class: "FileInventory",
  inventory_tool: "dd-inventory",
  inventory_tool_version: "0.1.0",
  inventory_made_at: "2026-11-01T09:00:00+00:00",
  inventory_files: [
    {
      file_path: "readings.csv",
      file_size: 100,
      file_sha256: "0".repeat(64),
      file_media_type: "text/csv",
      file_pronom_ids: ["x-fmt/18"],
      file_identified_by: "extension",
    },
  ],
};

const SAVED: SavedInventory = {
  digest: "d1",
  file_count: 1,
  inventory_made_at: INVENTORY.inventory_made_at,
  added_at: "2026-11-10T10:00:00+00:00",
  revises: null,
};

function renderAdd(api: Partial<ProjectApi>, onSaved = vi.fn()) {
  const { container } = render(
    <ProjectApiContext.Provider value={{ ...httpProjectApi, ...api }}>
      <AddInventory projectId="p1" onSaved={onSaved} />
    </ProjectApiContext.Provider>,
  );
  return { onSaved, input: container.querySelector<HTMLInputElement>('input[type="file"]') };
}

function json(content: unknown, name = "inventory.json") {
  return new File([JSON.stringify(content)], name, { type: "application/json" });
}

describe("AddInventory", () => {
  it("saves a chosen inventory to the project only once it is confirmed", async () => {
    const saveInventory = vi.fn<ProjectApi["saveInventory"]>().mockResolvedValue(SAVED);
    const { onSaved, input } = renderAdd({ saveInventory });
    await userEvent.upload(input as HTMLInputElement, json(INVENTORY));
    const dialog = await screen.findByRole("dialog", { name: "Check the inventory before attaching it" });
    expect(saveInventory).not.toHaveBeenCalled();
    await userEvent.click(within(dialog).getByRole("button", { name: "Add this inventory" }));
    await waitFor(() => expect(onSaved).toHaveBeenCalledWith(SAVED));
    expect(saveInventory.mock.calls[0]?.[0]).toBe("p1");
    expect((saveInventory.mock.calls[0]?.[1] as FileInventory).inventory_files).toHaveLength(1);
    expect(screen.getByText("Inventory added to the project.")).toBeInTheDocument();
  });

  it("saves nothing when the check is cancelled", async () => {
    const saveInventory = vi.fn<ProjectApi["saveInventory"]>();
    const { input } = renderAdd({ saveInventory });
    await userEvent.upload(input as HTMLInputElement, json(INVENTORY));
    const dialog = await screen.findByRole("dialog");
    await userEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(saveInventory).not.toHaveBeenCalled();
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("says why a file is not an inventory", async () => {
    const { input } = renderAdd({});
    await userEvent.upload(input as HTMLInputElement, json({ hello: "world" }, "notes.json"));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("keeps the check open and says so when the project refuses the inventory", async () => {
    const saveInventory = vi.fn<ProjectApi["saveInventory"]>().mockRejectedValue(new Error("the server answered 400"));
    const { onSaved, input } = renderAdd({ saveInventory });
    await userEvent.upload(input as HTMLInputElement, json(INVENTORY));
    const dialog = await screen.findByRole("dialog");
    await userEvent.click(within(dialog).getByRole("button", { name: "Add this inventory" }));
    expect(await screen.findByText(/was not added: the server answered 400/)).toBeInTheDocument();
    expect(onSaved).not.toHaveBeenCalled();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });
});
