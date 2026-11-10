import {
  applyEdits,
  NO_EDITS,
  type FileInventory,
  type InventoryEdits,
  type InventoryFile,
} from "@data-director/inventory";
import { useState } from "react";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";

import { record, startHistory } from "./history";
import { InventoryDialog } from "./InventoryDialog";
import { InventoryView, SHOWN } from "./InventoryView";

function file(path: string, overrides: Partial<InventoryFile> = {}): InventoryFile {
  return {
    file_path: path,
    file_size: 1500,
    file_sha256: "0".repeat(64),
    file_media_type: "text/csv",
    file_pronom_ids: ["x-fmt/18"],
    file_identified_by: "extension",
    ...overrides,
  };
}

const INVENTORY: FileInventory = {
  schema_class: "FileInventory",
  inventory_files: [
    file("README.md", { file_media_type: "text/markdown", file_pronom_ids: ["fmt/1149"] }),
    file("data/readings.csv", {
      file_fields: [
        { name: "site", field_type: "string" },
        { name: "participant_name", field_type: "string" },
      ],
    }),
    file("data/raw/2026.csv"),
    file("docs/protocol.pdf", {
      file_media_type: "application/pdf",
      file_pronom_ids: ["fmt/18", "fmt/19"],
      file_identified_by: "signature",
      file_size: 2_000_000,
    }),
    file("docs/blob.bin", { file_identified_by: "none", file_pronom_ids: [] }),
  ],
  inventory_tool: "dd-inventory",
  inventory_tool_version: "0.1.0",
  inventory_identified_with: "fido 1.6.1 with PRONOM signatures v109",
  inventory_made_at: "2026-10-30T15:06:19+00:00",
  inventory_limitations: ["2 hidden files were skipped."],
};

describe("InventoryView", () => {
  it("says what the inventory amounts to and what it leaves out", async () => {
    const { container } = render(<InventoryView inventory={INVENTORY} />);
    expect(screen.getByText(/everything the inventory holds/)).toBeInTheDocument();
    expect(screen.getByText("5 files, 2 MB in all")).toBeInTheDocument();
    expect(screen.getByText("30 Oct 2026 by dd-inventory 0.1.0")).toBeInTheDocument();
    expect(screen.getByText(INVENTORY.inventory_identified_with as string)).toBeInTheDocument();
    expect(screen.getByText("Guessed from its name: 3 files")).toBeInTheDocument();
    expect(screen.getByText("Not recognised: 1 file")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "What it leaves out" })).toBeInTheDocument();
    expect(screen.getByText("2 hidden files were skipped.")).toBeInTheDocument();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("lists formats largest first, linking each PRONOM identifier", () => {
    render(<InventoryView inventory={INVENTORY} />);
    const formats = screen.getByRole("region", { name: "Formats" });
    const rows = within(formats).getAllByRole("row").slice(1);
    expect(rows.map((r) => within(r).getAllByRole("cell")[0]?.textContent)).toEqual([
      "application/pdf",
      "text/csv",
      "text/markdown",
    ]);
    expect(within(formats).getByRole("link", { name: "fmt/18" })).toHaveAttribute(
      "href",
      "https://www.nationalarchives.gov.uk/PRONOM/fmt/18",
    );
  });

  it("shows folders closed, and their files once opened", async () => {
    render(<InventoryView inventory={INVENTORY} />);
    const files = screen.getByRole("region", { name: "Files" });
    expect(within(files).getByText("README.md")).toBeVisible();
    expect(within(files).queryByText("protocol.pdf")).toBeNull();
    await userEvent.click(within(files).getByText("docs/"));
    expect(within(files).getByText("protocol.pdf")).toBeInTheDocument();
    expect(within(files).getByText("Could be any of 2 formats")).toBeInTheDocument();
    expect(within(files).getByText("Not recognised")).toBeInTheDocument();
  });

  it("finds files by name or column heading", async () => {
    render(<InventoryView inventory={INVENTORY} />);
    const search = screen.getByRole("textbox", { name: "Find files" });
    await userEvent.type(search, "participant");
    expect(screen.getByRole("status")).toHaveTextContent("1 file matches.");
    expect(screen.getAllByText("data/readings.csv").length).toBeGreaterThan(0);
    await userEvent.clear(search);
    await userEvent.type(search, "nothing like it");
    expect(screen.getByRole("status")).toHaveTextContent("No file matches.");
  });

  it("draws only the first matches of a large inventory", async () => {
    const many = Array.from({ length: SHOWN + 5 }, (_, i) => file(`data/${i}.csv`));
    render(<InventoryView inventory={{ ...INVENTORY, inventory_files: many }} />);
    await userEvent.type(screen.getByRole("textbox", { name: "Find files" }), ".csv");
    expect(screen.getByRole("status")).toHaveTextContent(`${SHOWN + 5} files match; the first ${SHOWN}`);
    const list = screen.getByRole("region", { name: "Files" }).querySelector("ul");
    expect(list?.children).toHaveLength(SHOWN);
  });

  it("gives each table's columns and their types", async () => {
    render(<InventoryView inventory={INVENTORY} />);
    const tables = screen.getByRole("region", { name: "Tables" });
    await userEvent.click(within(tables).getByText("data/readings.csv"));
    const table = within(tables).getByRole("table", { name: "Columns of data/readings.csv" });
    expect(within(table).getByText("participant_name")).toBeInTheDocument();
  });

  it("says when there are no files", () => {
    render(<InventoryView inventory={{ ...INVENTORY, inventory_files: [], inventory_limitations: [] }} />);
    expect(screen.getByText("The inventory lists no files.")).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Formats" })).toBeNull();
    expect(screen.queryByRole("region", { name: "Tables" })).toBeNull();
  });
});

describe("InventoryView, editing", () => {
  let edits: InventoryEdits = NO_EDITS;
  function Editing() {
    const [history, setHistory] = useState(startHistory);
    edits = history.present;
    return (
      <InventoryView
        inventory={INVENTORY}
        editing={{
          edits: history.present,
          dispatch: (action) => setHistory((h) => record(h, INVENTORY, action)),
        }}
      />
    );
  }
  const latest = {
    get paths() {
      return edits.omitted.paths;
    },
    get columns() {
      return edits.omitted.columns;
    },
  };

  it("offers no checkboxes when read-only", () => {
    render(<InventoryView inventory={INVENTORY} />);
    expect(screen.queryByRole("checkbox")).toBeNull();
  });

  it("leaves out a folder, unopened, with every file beneath it", async () => {
    const { container } = render(<Editing />);
    expect(screen.getByRole("status")).toHaveTextContent("Nothing is left out or changed.");
    const folder = screen.getByRole("checkbox", { name: "Include the folder docs/" });
    expect(folder).toBeChecked();
    await userEvent.click(folder);
    expect(folder).not.toBeChecked();
    expect(latest.paths).toEqual(new Set(["docs"]));
    expect(screen.getByRole("status")).toHaveTextContent("2 files left out");
    // Its files show as left out, and stay so until the folder is included again.
    await userEvent.click(screen.getByText("docs/"));
    const pdf = screen.getByRole("checkbox", { name: "Include docs/protocol.pdf" });
    expect(pdf).not.toBeChecked();
    expect(pdf).toBeDisabled();
    expect(await axe(container)).toHaveNoViolations();
    await userEvent.click(folder);
    expect(pdf).toBeChecked();
    expect(pdf).toBeEnabled();
    expect(screen.getByRole("status")).toHaveTextContent("Nothing is left out or changed.");
  });

  it("leaves out a file found by search, and a column of a table", async () => {
    render(<Editing />);
    await userEvent.type(screen.getByRole("textbox", { name: "Find files" }), "participant");
    await userEvent.click(screen.getByRole("checkbox", { name: "Include data/readings.csv" }));
    expect(latest.paths).toEqual(new Set(["data/readings.csv"]));
    // A table left out leaves its columns out with it.
    const tables = screen.getByRole("region", { name: "Tables" });
    await userEvent.click(within(tables).getByText("data/readings.csv"));
    const column = within(tables).getByRole("checkbox", {
      name: "Include the column participant_name of data/readings.csv",
    });
    expect(column).toBeDisabled();
    await userEvent.click(screen.getByRole("checkbox", { name: "Include data/readings.csv" }));
    await userEvent.click(column);
    expect(latest.columns).toEqual(new Map([["data/readings.csv", new Set(["participant_name"])]]));
    expect(screen.getByText(/1 column left out/)).toBeInTheDocument();
    await userEvent.click(column);
    expect(latest.columns.size).toBe(0);
  });
});

/** The list item of the file or folder named `name` in the tree or a list of matches. */
function row(name: string): HTMLElement {
  const item = screen.getByText(name, { selector: ".inventory-file-name" }).closest("li");
  if (!item) throw new Error(`no row for ${name}`);
  return item;
}

describe("InventoryView, stating what the command cannot know", () => {
  let edits: InventoryEdits = NO_EDITS;
  function Editing() {
    const [history, setHistory] = useState(startHistory);
    edits = history.present;
    return (
      <InventoryView
        inventory={INVENTORY}
        editing={{
          edits: history.present,
          dispatch: (action) => setHistory((h) => record(h, INVENTORY, action)),
          newPaths: new Set(["README.md"]),
        }}
      />
    );
  }

  it("describes a file and gives the part it plays, shown in place", async () => {
    const { container } = render(<Editing />);
    await userEvent.click(within(row("README.md")).getByText("Describe"));
    await userEvent.type(screen.getByRole("textbox", { name: "What this file is" }), "How the survey was run");
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Part it plays" }), "documentation");
    const readme = applyEdits(INVENTORY, edits).inventory_files?.find((f) => f.file_path === "README.md");
    expect(readme).toMatchObject({ file_description: "How the survey was run", file_role: "documentation" });
    expect(screen.getByText("How the survey was run", { selector: ".inventory-description" })).toBeInTheDocument();
    expect(screen.getByText("New in this scan")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("1 description; 1 role");
    expect(await axe(container)).toHaveNoViolations();
  });

  it("chooses one of the formats the command found, and nothing outside them", async () => {
    render(<Editing />);
    await userEvent.click(screen.getByText("docs/"));
    const pdf = row("protocol.pdf");
    await userEvent.click(within(pdf).getByText("Describe"));
    expect(within(pdf).getAllByRole("radio")).toHaveLength(3);
    await userEvent.click(within(pdf).getByRole("radio", { name: "fmt/19" }));
    const chosen = applyEdits(INVENTORY, edits).inventory_files?.find((f) => f.file_path === "docs/protocol.pdf");
    expect(chosen).toMatchObject({ file_pronom_ids: ["fmt/19"], file_identified_by: "researcher" });
    expect(within(pdf).getByText("Format chosen by you")).toBeInTheDocument();
    // A format guessed from the name alone has one match: a media type may be given, not a choice.
    const readme = row("README.md");
    await userEvent.click(within(readme).getByText("Describe"));
    expect(within(readme).getByRole("group", { name: "Format" })).toBeInTheDocument();
    expect(within(readme).queryByRole("radio")).toBeNull();
  });

  it("gives every file in a folder a part with one choice, and describes a column", async () => {
    render(<Editing />);
    await userEvent.click(screen.getByText("data/"));
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Part every file in data/ plays" }), "data");
    expect(edits.files.get("data/readings.csv")?.role).toBe("data");
    expect(edits.files.get("data/raw/2026.csv")?.role).toBe("data");
    const tables = screen.getByRole("region", { name: "Tables" });
    await userEvent.click(within(tables).getByText("data/readings.csv"));
    const site = within(tables).getByRole("textbox", { name: "Describe the column site of data/readings.csv" });
    await userEvent.type(site, "Site code");
    await userEvent.tab();
    expect(edits.fields.get("data/readings.csv")?.get("site")).toBe("Site code");
  });

  it("shows only the files worth a look when asked", async () => {
    render(<Editing />);
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Show" }), "attention");
    const files = screen.getByRole("region", { name: "Files" });
    const named = () => [...files.querySelectorAll(".inventory-file-name")].map((e) => e.textContent);
    expect(named()).toEqual(expect.arrayContaining(["docs/protocol.pdf", "data/readings.csv"]));
    expect(named()).not.toContain("data/raw/2026.csv");
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Show" }), "new");
    expect(named()).toEqual(["README.md"]);
  });
});

describe("InventoryDialog", () => {
  it("opens the inventory in hand and closes again", async () => {
    render(<InventoryDialog source={{ document: INVENTORY }} />);
    await userEvent.click(screen.getByRole("button", { name: "View inventory" }));
    const dialog = screen.getByRole("dialog", { name: "What the inventory holds" });
    expect(within(dialog).getByText("5 files, 2 MB in all")).toBeInTheDocument();
    expect(await axe(dialog)).toHaveNoViolations();
    await userEvent.click(within(dialog).getByRole("button", { name: "Close" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    await waitFor(() => expect(screen.getByRole("button", { name: "View inventory" })).toHaveFocus());
  });

  it("fetches a project's inventory when opened", async () => {
    const load = vi.fn(() => Promise.resolve<unknown>(INVENTORY));
    render(<InventoryDialog source={{ load }} />);
    expect(load).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "View inventory" }));
    expect(await screen.findByText("5 files, 2 MB in all")).toBeInTheDocument();
    expect(load).toHaveBeenCalledTimes(1);
  });

  it.each([
    ["the server fails", () => Promise.reject(new Error("the server answered 500")), /answered 500/],
    ["it is not an inventory", () => Promise.resolve({ schema_class: "Message" }), /FileInventory/],
  ])("says so when %s", async (_, load, message) => {
    render(<InventoryDialog source={{ load }} />);
    await userEvent.click(screen.getByRole("button", { name: "View inventory" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(message);
  });
});
