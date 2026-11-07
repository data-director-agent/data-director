import { MAKING_AN_INVENTORY } from "@data-director/inventory";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";

import { browserSystem, MakeInventoryDialog } from "./MakeInventoryDialog";

function withPlatform(platform: string) {
  vi.spyOn(navigator, "platform", "get").mockReturnValue(platform);
}

afterEach(() => vi.restoreAllMocks());

async function open(onAttach: (file: File) => void = () => undefined) {
  const user = userEvent.setup();
  render(<MakeInventoryDialog onAttach={onAttach} />);
  await user.click(screen.getByRole("button", { name: "Make an inventory" }));
  return { user, dialog: await screen.findByRole("dialog", { name: "Make an inventory" }) };
}

describe("MakeInventoryDialog", () => {
  it("says what an inventory is, and shows the commands for this computer's system first", async () => {
    withPlatform("MacIntel");
    const { dialog } = await open();
    expect(within(dialog).getByText(MAKING_AN_INVENTORY.summary)).toBeVisible();
    const tab = within(dialog).getByRole("tab", { name: /macOS/ });
    expect(tab).toHaveAttribute("aria-selected", "true");
    expect(tab).toHaveAccessibleName("macOS, this computer");
    const panel = within(dialog).getByRole("tabpanel");
    expect(within(panel).getByText("curl -LsSf https://astral.sh/uv/install.sh | sh")).toBeVisible();
    expect(
      within(panel).getByText("uvx data-director-inventory path/to/dataset -o inventory.json"),
    ).toBeVisible();
    expect(within(dialog).getByRole("link", { name: /user guide/ })).toHaveAttribute(
      "href",
      expect.stringContaining("/user-guide/making-an-inventory/"),
    );
    expect(await axe(document.body)).toHaveNoViolations();
  });

  it("keeps the other systems one step away", async () => {
    withPlatform("Win32");
    const { user, dialog } = await open();
    expect(within(dialog).getByRole("tab", { name: /Windows/ })).toHaveAttribute("aria-selected", "true");
    expect(within(dialog).getByText(/install\.ps1/)).toBeVisible();
    await user.click(within(dialog).getByRole("tab", { name: "Linux" }));
    const panel = within(dialog).getByRole("tabpanel");
    expect(within(panel).getByText(/Sign in to it as you usually do/i)).toBeVisible();
  });

  it("starts at the first system when the browser's is not covered", async () => {
    withPlatform("iPhone");
    const { dialog } = await open();
    expect(within(dialog).getByRole("tab", { name: "Windows" })).toHaveAttribute("aria-selected", "true");
  });

  it("copies a command exactly and says so", async () => {
    withPlatform("Linux x86_64");
    const { user, dialog } = await open();
    await user.click(
      within(dialog).getByRole("button", { name: "Copy the command that makes the inventory on Linux" }),
    );
    expect(await navigator.clipboard.readText()).toBe(
      "uvx data-director-inventory path/to/dataset -o inventory.json",
    );
    expect(within(dialog).getByText("Copied.")).toBeVisible();
  });

  it("says when the command could not be copied", async () => {
    withPlatform("Linux x86_64");
    const { user, dialog } = await open();
    vi.spyOn(navigator.clipboard, "writeText").mockRejectedValue(new Error("denied"));
    await user.click(
      within(dialog).getByRole("button", { name: "Copy the command that installs uv on Linux" }),
    );
    expect(await within(dialog).findByText(/Could not copy/)).toBeVisible();
  });

  it("ends at the file picker, and closes once a file is chosen", async () => {
    const onAttach = vi.fn();
    const { user, dialog } = await open(onAttach);
    const input = dialog.querySelector<HTMLInputElement>('input[type="file"]');
    if (!input) throw new Error("no file input");
    const chosen = new File(["{}"], "inventory.json", { type: "application/json" });
    await user.upload(input, chosen);
    expect(onAttach).toHaveBeenCalledWith(chosen);
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });
});

describe("browserSystem", () => {
  it("prefers the client hint to the legacy platform", () => {
    const nav = { platform: "Linux x86_64", userAgentData: { platform: "Windows" } } as unknown as Navigator;
    expect(browserSystem(nav)).toBe("windows");
  });

  it("falls back to the legacy platform, and to null with no navigator", () => {
    expect(browserSystem({ platform: "MacIntel" } as Navigator)).toBe("macos");
    expect(browserSystem(undefined)).toBeNull();
  });
});
