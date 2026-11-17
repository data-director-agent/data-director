import type { ChosenFolder, ScanEvent, ScanOutcome } from "@data-director/inventory";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";

import { pageScanner, setPageScanner, type Scanner } from "../../scan/scanner";
import { AnnouncerProvider } from "../ui/Announcer";
import { DescribeFolder } from "./DescribeFolder";
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

function renderPanel(scanner: Scanner, onDescribed: (file: File) => void = () => undefined) {
  return render(
    <AnnouncerProvider>
      <DescribeFolder scanner={scanner} onDescribed={onDescribed} />
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
  it("is not offered where the deployment does not serve the scanner", async () => {
    const { scanner } = drivenScanner(false);
    const available = vi.spyOn(scanner, "available");
    renderPanel(scanner);
    await waitFor(() => expect(available).toHaveBeenCalled());
    expect(screen.queryByRole("region", { name: /Describe a folder/ })).toBeNull();
  });

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
  beforeEach(() => setPageScanner(drivenScanner().scanner));
  afterEach(() => setPageScanner(unserved));

  it("offers to describe a folder first, then the command", async () => {
    const user = userEvent.setup();
    render(
      <AnnouncerProvider>
        <MakeInventoryDialog onAttach={() => undefined} />
      </AnnouncerProvider>,
    );
    await user.click(screen.getByRole("button", { name: "Make an inventory" }));
    const dialog = await screen.findByRole("dialog", { name: "Make an inventory" });
    await within(dialog).findByRole("region", { name: "Describe a folder in this browser" });
    const headings = within(dialog)
      .getAllByRole("heading", { level: 3 })
      .map((h) => h.textContent);
    expect(headings).toEqual([
      "Describe a folder in this browser",
      "Make it with the command",
      "Attach it",
    ]);
  });
});
