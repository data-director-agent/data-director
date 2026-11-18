import { act, renderHook } from "@testing-library/react";
import { onTestFinished } from "vitest";
import type { ClipboardEvent, DragEvent } from "react";

import { readDocument } from "../../conversation/documentation";
import { readInventory } from "../../conversation/inventory";
import { useAttachments } from "./useAttachments";

const INVENTORY = JSON.stringify({
  schema_class: "FileInventory",
  inventory_tool: "dd-inventory",
  inventory_tool_version: "0.1.0",
  inventory_made_at: "2026-11-01T09:00:00Z",
  inventory_files: ["a.csv", "b.csv"].map((file_path) => ({
    file_path,
    file_size: 10,
    file_sha256: "0".repeat(64),
    file_identified_by: "extension",
  })),
});
const PROTOCOL = "# Sampling protocol\n\nSediment cores were taken monthly.\n";

function render(documents = true) {
  const box = { current: document.createElement("textarea") };
  document.body.append(box.current);
  onTestFinished(() => box.current.remove());
  const announce = vi.fn<(said: string) => void>();
  const view = renderHook(() => useAttachments(box, announce, documents));
  return { ...view, announce, box };
}

function paste(text: string) {
  const event = {
    clipboardData: { getData: () => text },
    preventDefault: vi.fn(),
  };
  return event as unknown as ClipboardEvent<HTMLTextAreaElement> & typeof event;
}

function drag(files: File[]) {
  const event = {
    dataTransfer: { types: files.length ? ["Files"] : ["text/plain"], files },
    preventDefault: vi.fn(),
  };
  return event as unknown as DragEvent<HTMLFormElement> & typeof event;
}

describe("useAttachments", () => {
  it("opens a chosen document to be checked, by its name", async () => {
    const { result } = render();
    await act(() => result.current.attachFile(new File([PROTOCOL], "protocol.md")));
    expect(result.current.pendingDocument?.name).toBe("protocol.md");
    expect(result.current.pendingInventory).toBeNull();
    expect(result.current.carries).toBe(false);
  });

  it("takes no document where the profile refuses them, but still an inventory", async () => {
    const { result } = render(false);
    expect(result.current.documents).toBe(false);
    await act(() => result.current.attachFile(new File([PROTOCOL], "protocol.md")));
    expect(result.current.pendingDocument).toBeNull();
    expect(result.current.error).toBeTruthy();
    await act(() => result.current.attachFile(new File([INVENTORY], "inventory.json")));
    expect(result.current.pendingInventory?.fileCount).toBe(2);
  });

  it("sends a PDF to be read on the server and opens its text to be checked", async () => {
    const fetched = vi.fn(() =>
      Promise.resolve(new Response(JSON.stringify({ name: "plan.pdf", text: PROTOCOL, size: 50 }))),
    );
    vi.stubGlobal("fetch", fetched);
    onTestFinished(() => {
      vi.unstubAllGlobals();
    });
    const { result } = render();
    await act(() => result.current.attachFile(new File(["%PDF-1.4"], "plan.pdf")));
    expect(fetched).toHaveBeenCalledWith("/api/documentation/extract", expect.anything());
    expect(result.current.pendingDocument?.text).toBe(PROTOCOL);
    expect(result.current.pendingDocument?.data).toBeTruthy();
  });

  it("refuses a PDF over the size a project keeps without sending it", async () => {
    const fetched = vi.fn();
    vi.stubGlobal("fetch", fetched);
    onTestFinished(() => {
      vi.unstubAllGlobals();
    });
    const { result } = render();
    const big = new File([new Uint8Array(1024 * 1024 + 1)], "plan.pdf");
    await act(() => result.current.attachFile(big));
    expect(fetched).not.toHaveBeenCalled();
    expect(result.current.pendingDocument).toBeNull();
    expect(result.current.error).toBeTruthy();
  });

  it("opens any other file as an inventory to be checked", async () => {
    const { result } = render();
    await act(() => result.current.attachFile(new File([INVENTORY], "inventory.json")));
    expect(result.current.pendingInventory?.fileCount).toBe(2);
    expect(result.current.pendingDocument).toBeNull();
  });

  it("says why a file cannot be attached, and attaches nothing", async () => {
    const { result } = render();
    await act(() => result.current.attachFile(new File(["  \n"], "protocol.md")));
    expect(result.current.error).toBeTruthy();
    await act(() => result.current.attachFile(new File(["not json"], "inventory.json")));
    expect(result.current.error).toBeTruthy();
    expect(result.current.pendingDocument).toBeNull();
    expect(result.current.pendingInventory).toBeNull();
    act(() => result.current.clearError());
    expect(result.current.error).toBeNull();
  });

  it("attaches a checked inventory and document, and removes them", () => {
    const { result, announce, box } = render();
    act(() => result.current.confirmInventory(readInventory(INVENTORY, null)));
    act(() => result.current.confirmDocument(readDocument(PROTOCOL, "protocol.md")));
    expect(result.current.inventory?.fileCount).toBe(2);
    expect(result.current.document?.name).toBe("protocol.md");
    expect(result.current.carries).toBe(true);
    act(() => result.current.removeInventory());
    act(() => result.current.removeDocument());
    expect(result.current.carries).toBe(false);
    expect(announce).toHaveBeenCalledTimes(4);
    expect(box.current).toHaveFocus();
  });

  it("attaches nothing when a check is cancelled", () => {
    const { result, announce } = render();
    act(() => result.current.discardInventory());
    act(() => result.current.discardDocument());
    expect(result.current.carries).toBe(false);
    expect(announce).toHaveBeenCalledTimes(2);
  });

  it("turns a pasted inventory into one to check, not text, and pastes other text as it is", () => {
    const { result } = render();
    const pasted = paste(INVENTORY);
    act(() => result.current.onPaste(pasted));
    expect(pasted.preventDefault).toHaveBeenCalled();
    expect(result.current.pendingInventory?.name).toBeNull();
    const other = paste("hello");
    act(() => result.current.onPaste(other));
    expect(other.preventDefault).not.toHaveBeenCalled();
  });

  it("takes a dropped file, and ignores a drag that carries none", async () => {
    const { result } = render();
    act(() => result.current.onDragOver(drag([])));
    expect(result.current.dropping).toBe(false);
    act(() => result.current.onDragOver(drag([new File([PROTOCOL], "protocol.md")])));
    expect(result.current.dropping).toBe(true);
    act(() => result.current.onDragLeave());
    expect(result.current.dropping).toBe(false);
    await act(async () => {
      result.current.onDrop(drag([new File([PROTOCOL], "protocol.md")]));
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
    expect(result.current.pendingDocument?.name).toBe("protocol.md");
  });

  it("puts back what a failed send carried", () => {
    const { result } = render();
    const inventory = readInventory(INVENTORY, null);
    act(() => result.current.restore({ inventory, document: null }));
    expect(result.current.inventory).toBe(inventory);
    expect(result.current.document).toBeNull();
  });
});
