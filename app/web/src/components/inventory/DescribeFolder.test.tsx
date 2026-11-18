import type { ChosenFolder, FileInventory, ScanEvent, ScanOutcome } from "@data-director/inventory";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";

import { httpProjectApi, ProjectApiContext, type ProjectApi, type SavedInventory } from "../../project/api";
import { pageScanner, setPageScanner, type Scanner } from "../../scan/scanner";
import { AnnouncerProvider } from "../ui/Announcer";
import { DescribeFolder } from "./DescribeFolder";
import { InventoryEditDialog } from "./InventoryEditDialog";
import { MakeInventoryDialog } from "./MakeInventoryDialog";

/** A scanner whose one scan the test drives: its events and its end. */
function drivenScanner(available = true) {
  const scans: {
    folder: ChosenFolder;
    emit: (event: ScanEvent) => void;
    end: (outcome: ScanOutcome) => void;
    cancelled: boolean;
  }[] = [];
  const scanner: Scanner = {
    available: () => Promise.resolve(available),
    scan(folder, onEvent) {
      let end!: (outcome: ScanOutcome) => void;
      const outcome = new Promise<ScanOutcome>((resolve) => (end = resolve));
      const scan = { folder, emit: onEvent, end, cancelled: false };
      scans.push(scan);
      return {
        outcome,
        cancel: () => {
          scan.cancelled = true;
          end({ status: "cancelled" });
        },
      };
    },
  };
  return { scanner, scans };
}

/** The first of `items`, which the test expects there to be. */
function first<T>(items: readonly T[]): T {
  const [item] = items;
  if (item === undefined) throw new Error("expected at least one");
  return item;
}

function withPath(name: string, path: string, text = "a,b\n1,2\n"): File {
  const file = new File([text], name);
  Object.defineProperty(file, "webkitRelativePath", { value: path });
  return file;
}

/** A file that says it is `size` bytes long, as a very large one would. */
function sized(file: File, size: number): File {
  Object.defineProperty(file, "size", { value: size });
  return file;
}

type PanelProps = Partial<Parameters<typeof DescribeFolder>[0]>;

function renderPanel(scanner: Scanner, onDescribed: (file: File) => void = () => undefined, props: PanelProps = {}) {
  return render(
    <AnnouncerProvider>
      <DescribeFolder scanner={scanner} onDescribed={onDescribed} {...props} />
    </AnnouncerProvider>,
  );
}

async function section() {
  return screen.findByRole("region", { name: "Describe a folder in this browser" });
}

function folderInput(): HTMLInputElement {
  const input = document.querySelector<HTMLInputElement>('input[type="file"]');
  if (!input) throw new Error("no file input");
  return input;
}

const polite = () => screen.getByRole("log", { name: "Announcements" });
const errors = () => screen.getByRole("log", { name: "Errors" });

afterEach(() => {
  delete (window as { showDirectoryPicker?: unknown }).showDirectoryPicker;
});

describe("DescribeFolder", () => {
  it("says no file is sent, credits the signatures and links to the notices", async () => {
    renderPanel(drivenScanner().scanner);
    const panel = await section();
    expect(within(panel).getByText(/None of the files is sent anywhere/)).toBeVisible();
    expect(within(panel).getByText(/Open Government Licence v3\.0/)).toBeVisible();
    expect(within(panel).getByRole("link", { name: "Licence notices" })).toHaveAttribute(
      "href",
      "inventory-bundle/NOTICES.md",
    );
    expect(await axe(document.body)).toHaveNoViolations();
  });

  it("offers no folder while it is disabled, by button or by drop", async () => {
    const { scanner, scans } = drivenScanner();
    renderPanel(scanner, undefined, { isDisabled: true });
    const panel = await section();
    expect(within(panel).getByRole("button", { name: "Choose a folder…" })).toBeDisabled();
    const drop = new Event("drop", { bubbles: true, cancelable: true });
    Object.defineProperty(drop, "dataTransfer", { value: { types: ["Files"], items: [] } });
    act(() => panel.dispatchEvent(drop));
    expect(drop.defaultPrevented).toBe(false);
    expect(scans).toEqual([]);
  });

  it("says, when it updates an inventory, that nothing is kept before saving", async () => {
    renderPanel(drivenScanner().scanner, undefined, { purpose: "update" });
    expect(within(await section()).getByText(/nothing is kept until you save/)).toBeVisible();
  });

  it("describes a folder chosen with the folder input and hands on the inventory as a file", async () => {
    const { scanner, scans } = drivenScanner();
    const onDescribed = vi.fn();
    renderPanel(scanner, onDescribed);
    await section();
    await userEvent.upload(folderInput(), [
      withPath("b.csv", "survey/tables/b.csv"),
      withPath("a.csv", "survey/a.csv"),
    ]);
    const scan = first(scans);
    expect(scan.folder.name).toBe("survey");
    expect(scan.folder.files.map((f) => f.path)).toEqual(["a.csv", "tables/b.csv"]);
    expect(
      within(polite()).getByText(/Describing survey\. Fetching the scanner\./),
    ).toBeInTheDocument();

    act(() => scan.emit({ type: "stage", stage: "reading" }));
    act(() => scan.emit({ type: "progress", path: "a.csv", size: 8, done: 1, total: 2 }));
    const progress = screen.getByRole("progressbar", {
      name: /Describing survey: Reading the files\. 1 of 2 files\./,
    });
    expect(progress).toHaveAttribute("value", "1");
    expect(progress).toHaveAttribute("max", "2");
    expect(within(polite()).getByText("Reading the files.")).toBeInTheDocument();
    expect(within(polite()).queryByText(/a\.csv/)).toBeNull();
    expect(await axe(document.body)).toHaveNoViolations();

    await act(async () => scan.end({ status: "done", inventory: '{"inventory_files":[]}' }));
    expect(onDescribed).toHaveBeenCalledTimes(1);
    const file = first(onDescribed.mock.calls)[0] as File;
    expect(file.name).toBe("survey-inventory.json");
    expect(file.type).toBe("application/json");
    expect(await file.text()).toBe('{"inventory_files":[]}');
  });

  it("prefers the directory picker, and does nothing when it is closed without a choice", async () => {
    const { scanner, scans } = drivenScanner();
    const user = userEvent.setup();
    const file = new File(["x"], "a.csv");
    const handle = {
      kind: "directory" as const,
      name: "survey",
      async *values() {
        yield { kind: "file" as const, name: "a.csv", getFile: async () => file };
      },
    };
    const picker = vi
      .fn()
      .mockRejectedValueOnce(new DOMException("closed", "AbortError"))
      .mockResolvedValueOnce(handle);
    (window as { showDirectoryPicker?: unknown }).showDirectoryPicker = picker;
    renderPanel(scanner);
    const panel = await section();
    expect(panel.querySelector('input[type="file"]')).toBeNull();
    const choose = within(panel).getByRole("button", { name: "Choose a folder…" });
    await user.click(choose);
    expect(scans).toEqual([]);
    expect(within(errors()).queryByText(/./)).toBeNull();
    await user.click(choose);
    await waitFor(() => expect(scans).toHaveLength(1));
    expect(picker).toHaveBeenCalledWith({ mode: "read" });
    expect(first(scans).folder).toEqual({ name: "survey", files: [{ path: "a.csv", file }] });
  });

  it("says why a choice cannot be described, in the assertive region", async () => {
    renderPanel(drivenScanner().scanner);
    await section();
    await userEvent.upload(folderInput(), [withPath("a.csv", "a.csv")]);
    const message = "Choose a folder, not separate files, to describe.";
    expect(within(errors()).getByText(message)).toBeInTheDocument();
    expect(within(await section()).getByText(message)).toBeVisible();
  });

  it("says a scan failed, in the assertive region, and offers the choice again", async () => {
    const { scanner, scans } = drivenScanner();
    const onDescribed = vi.fn();
    renderPanel(scanner, onDescribed);
    await section();
    await userEvent.upload(folderInput(), [withPath("a.csv", "survey/a.csv")]);
    await act(async () =>
      first(scans).end({ status: "failed", reason: "The folder could not be described: boom" }),
    );
    expect(within(errors()).getByText(/could not be described: boom/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Choose a folder…" })).toBeVisible();
    expect(onDescribed).not.toHaveBeenCalled();
  });

  it("stops a scan on Cancel and says so", async () => {
    const { scanner, scans } = drivenScanner();
    const user = userEvent.setup();
    const onDescribed = vi.fn();
    renderPanel(scanner, onDescribed);
    await section();
    await user.upload(folderInput(), [withPath("a.csv", "survey/a.csv")]);
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(first(scans).cancelled).toBe(true);
    expect(await within(polite()).findByText("Stopped describing the folder.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Choose a folder…" })).toBeVisible();
    expect(onDescribed).not.toHaveBeenCalled();
  });

  it("advises the command before describing a folder with a very large file", async () => {
    const { scanner, scans } = drivenScanner();
    const user = userEvent.setup();
    renderPanel(scanner);
    await section();
    await user.upload(folderInput(), [
      withPath("a.csv", "survey/a.csv"),
      sized(withPath("big.tif", "survey/images/big.tif"), 5_200_000_000),
    ]);
    const advice = screen.getByText(/survey holds a file of 5\.2 GB, images\/big\.tif\./);
    expect(advice).toHaveTextContent(/may close the page if it runs short/);
    expect(advice).toHaveFocus();
    expect(scans).toEqual([]);
    expect(await axe(document.body)).toHaveNoViolations();

    await user.click(screen.getByRole("button", { name: "Describe it here anyway" }));
    expect(first(scans).folder.files.map((f) => f.path)).toEqual(["a.csv", "images/big.tif"]);
    expect(screen.getByRole("progressbar")).toBeVisible();
  });

  it("goes back to choosing a folder when the advice is cancelled", async () => {
    const { scanner, scans } = drivenScanner();
    const user = userEvent.setup();
    renderPanel(scanner);
    await section();
    await user.upload(folderInput(), [sized(withPath("big.bin", "survey/big.bin"), 4_000_000_000)]);
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(scans).toEqual([]);
    expect(screen.queryByText(/holds a file of/)).toBeNull();
    expect(screen.getByRole("button", { name: "Choose a folder…" })).toHaveFocus();
  });

  it("describes a folder whose files are all under 4 GB without asking", async () => {
    const { scanner, scans } = drivenScanner();
    renderPanel(scanner);
    await section();
    await userEvent.upload(folderInput(), [
      sized(withPath("big.bin", "survey/big.bin"), 3_999_999_999),
    ]);
    expect(scans).toHaveLength(1);
    expect(screen.queryByText(/holds a file of/)).toBeNull();
  });

  it("cancels a scan still running when the dialog closes", async () => {
    const { scanner, scans } = drivenScanner();
    const view = renderPanel(scanner);
    await section();
    await userEvent.upload(folderInput(), [withPath("a.csv", "survey/a.csv")]);
    view.unmount();
    expect(first(scans).cancelled).toBe(true);
  });
});

describe("MakeInventoryDialog with the scanner served", () => {
  const unserved = pageScanner();
  let driven: ReturnType<typeof drivenScanner>;
  beforeEach(() => {
    driven = drivenScanner();
    setPageScanner(driven.scanner);
  });
  afterEach(() => setPageScanner(unserved));

  async function openDialog() {
    const user = userEvent.setup();
    render(
      <AnnouncerProvider>
        <MakeInventoryDialog onAttach={() => undefined} />
      </AnnouncerProvider>,
    );
    await user.click(screen.getByRole("button", { name: "Make an inventory" }));
    const dialog = await screen.findByRole("dialog", { name: "Make an inventory" });
    await within(dialog).findByRole("tablist", { name: "How to make it" });
    return { user, dialog };
  }

  it("opens on describing a folder in this browser, with the command a tab away", async () => {
    const { dialog } = await openDialog();
    expect(within(dialog).getByRole("tab", { name: "In this browser" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(within(dialog).getByRole("tab", { name: "With the command" })).toHaveAttribute(
      "aria-selected",
      "false",
    );
    expect(
      within(dialog).getByRole("region", { name: "Describe a folder in this browser" }),
    ).toBeVisible();
    expect(within(dialog).queryByRole("tablist", { name: "Operating system" })).toBeNull();
    expect(await axe(document.body)).toHaveNoViolations();
  });

  it("goes to the command from the browser route's pointer", async () => {
    const { user, dialog } = await openDialog();
    await user.click(within(dialog).getByRole("button", { name: "Use the command instead" }));
    expect(within(dialog).getByRole("tab", { name: "With the command" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(within(dialog).getByRole("tablist", { name: "Operating system" })).toBeVisible();
    expect(within(dialog).getByRole("button", { name: "Choose inventory.json" })).toBeVisible();
    // Kept, so that a scan goes on, but out of reach.
    const kept = within(dialog).getByRole("region", { hidden: true, name: /Describe a folder/ });
    expect(kept.closest("[inert]")).not.toBeNull();
  });

  it("keeps a scan running while the command is shown", async () => {
    const { user, dialog } = await openDialog();
    await userEvent.upload(folderInput(), [withPath("a.csv", "survey/a.csv")]);
    await user.click(within(dialog).getByRole("tab", { name: "With the command" }));
    await user.click(within(dialog).getByRole("tab", { name: "In this browser" }));
    expect(first(driven.scans).cancelled).toBe(false);
    expect(within(dialog).getByRole("progressbar")).toBeVisible();
  });
});

describe("InventoryEditDialog with the scanner served", () => {
  const unserved = pageScanner();
  let driven: ReturnType<typeof drivenScanner>;
  beforeEach(() => {
    driven = drivenScanner();
    setPageScanner(driven.scanner);
  });
  afterEach(() => setPageScanner(unserved));

  const entry = (path: string, description?: string) => ({
    file_path: path,
    file_size: 8,
    file_sha256: "0".repeat(64),
    file_media_type: "text/csv",
    file_pronom_ids: ["x-fmt/18"],
    file_identified_by: "extension" as const,
    ...(description ? { file_description: description } : {}),
  });
  const stored: FileInventory = {
    schema_class: "FileInventory",
    inventory_tool: "dd-inventory",
    inventory_tool_version: "0.1.0",
    inventory_made_at: "2026-11-01T09:00:00+00:00",
    inventory_files: [entry("a.csv", "Readings by site")],
  };
  const saved: SavedInventory = {
    digest: "d2",
    file_count: 2,
    inventory_made_at: stored.inventory_made_at,
    added_at: "2026-11-10T10:00:00+00:00",
    revises: "d1",
    part_count: null,
  };

  async function openDialog(saveInventory: ProjectApi["saveInventory"]) {
    const api = { ...httpProjectApi, inventory: () => Promise.resolve(stored), saveInventory };
    render(
      <AnnouncerProvider>
        <ProjectApiContext.Provider value={api}>
          <InventoryEditDialog projectId="p1" />
        </ProjectApiContext.Provider>
      </AnnouncerProvider>,
    );
    await userEvent.click(screen.getByRole("button", { name: "Edit inventory" }));
    const dialog = await screen.findByRole("dialog", { name: "Edit the project's inventory" });
    const panel = await within(dialog).findByRole("region", { name: "Describe a folder in this browser" });
    return { dialog, panel };
  }

  it("takes a folder described here as the new scan, carrying over what was said", async () => {
    const saveInventory = vi.fn<ProjectApi["saveInventory"]>().mockResolvedValue(saved);
    const { dialog, panel } = await openDialog(saveInventory);
    await userEvent.upload(folderInput(), [withPath("a.csv", "survey/a.csv"), withPath("b.csv", "survey/b.csv")]);
    // Which folder the scan is of cannot change while the folder is described. The dialog hears
    // that the scan started from the panel's effect, a render later, so wait for it.
    await waitFor(() => expect(within(dialog).getByLabelText("Scan of")).toBeDisabled());
    expect(within(dialog).getByLabelText("New scan")).toBeDisabled();
    const rescan = {
      ...stored,
      inventory_made_at: "2026-11-09T09:00:00+00:00",
      inventory_files: [entry("a.csv"), entry("b.csv")],
    };
    act(() => first(driven.scans).end({ status: "done", inventory: JSON.stringify(rescan) }));
    await within(dialog).findByRole("region", { name: "What the new scan changed" });
    expect(within(panel).getByRole("button", { name: "Choose a folder…" })).toBeEnabled();
    await userEvent.click(within(dialog).getByRole("button", { name: "Save as the project's inventory" }));
    await waitFor(() => expect(saveInventory).toHaveBeenCalled());
    const sent = saveInventory.mock.calls[0]?.[1] as FileInventory;
    expect(sent.inventory_made_at).toBe(rescan.inventory_made_at);
    expect(sent.inventory_files?.map((f) => f.file_path)).toEqual(["a.csv", "b.csv"]);
    expect(sent.inventory_files?.[0]?.file_description).toBe("Readings by site");
  });

  it("offers no folder until a new folder and the one the inventory has are named", async () => {
    const { dialog, panel } = await openDialog(vi.fn());
    await userEvent.selectOptions(within(dialog).getByLabelText("Scan of"), "A folder the inventory does not have yet");
    const choose = within(panel).getByRole("button", { name: "Choose a folder…" });
    expect(choose).toBeDisabled();
    await userEvent.type(within(dialog).getByLabelText("Name of the new folder"), "instrument");
    await userEvent.type(within(dialog).getByLabelText("Name for the folder the inventory already has"), "lab");
    expect(choose).toBeEnabled();
  });
});
