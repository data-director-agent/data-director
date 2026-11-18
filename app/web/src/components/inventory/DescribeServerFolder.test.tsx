import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";

import { makeServerFolders, type ServerFolders } from "../../scan/serverFolders";
import { AnnouncerProvider } from "../ui/Announcer";
import { DescribeServerFolder } from "./DescribeServerFolder";

const TREE: Record<string, string[]> = {
  "": ["cores"],
  cores: ["site-a", "site-b"],
};
const INVENTORY = { schema_class: "FileInventory", inventory_files: [] };

/** Folders under one listed root, `data`, as the server would answer for them. */
function standIn(available = true): ServerFolders & { described: string[] } {
  const described: string[] = [];
  return {
    described,
    available: () => Promise.resolve(available),
    roots: () => Promise.resolve(["data"]),
    list: (root, path) => Promise.resolve({ root, path, folders: TREE[path] ?? [] }),
    describe: (_root, path) => {
      described.push(path);
      return Promise.resolve(JSON.stringify(INVENTORY));
    },
  };
}

function renderPanel(folders: ServerFolders, onDescribed: (file: File) => void = () => undefined) {
  return render(
    <AnnouncerProvider>
      <DescribeServerFolder folders={folders} onDescribed={onDescribed} />
    </AnnouncerProvider>,
  );
}

describe("DescribeServerFolder", () => {
  it("is not shown where the deployment names no folder", async () => {
    const folders = standIn(false);
    const available = vi.spyOn(folders, "available");
    renderPanel(folders);
    await waitFor(() => expect(available).toHaveBeenCalled());
    expect(screen.queryByRole("region")).not.toBeInTheDocument();
  });

  it("steps into a subfolder and hands on its inventory as a file", async () => {
    const user = userEvent.setup();
    const folders = standIn();
    const onDescribed = vi.fn();
    renderPanel(folders, onDescribed);
    const region = await screen.findByRole("region");
    await user.click(await within(region).findByRole("button", { name: "data" }));
    await user.click(await within(region).findByRole("button", { name: "cores" }));
    const list = await within(region).findByRole("list", { name: "Folders" });
    expect(within(list).getAllByRole("button")).toHaveLength(TREE.cores?.length ?? 0);
    expect(within(region).getByRole("navigation")).toBeInTheDocument();
    expect(await axe(document.body)).toHaveNoViolations();

    await user.click(within(region).getByRole("button", { name: /cores$/ }));
    await waitFor(() => expect(onDescribed).toHaveBeenCalledTimes(1));
    expect(folders.described).toEqual(["cores"]);
    const file = onDescribed.mock.calls[0]?.[0] as File;
    expect(file.name).toBe("cores-inventory.json");
    expect(JSON.parse(await file.text())).toEqual(INVENTORY);
  });

  it("goes back up by the trail", async () => {
    const user = userEvent.setup();
    renderPanel(standIn());
    const region = await screen.findByRole("region");
    await user.click(await within(region).findByRole("button", { name: "data" }));
    await user.click(await within(region).findByRole("button", { name: "cores" }));
    const trail = within(region).getByRole("navigation");
    await user.click(within(trail).getByRole("button", { name: "data" }));
    const list = await within(region).findByRole("list", { name: "Folders" });
    expect(within(list).getAllByRole("button")).toHaveLength(TREE[""]?.length ?? 0);
  });
});

describe("makeServerFolders", () => {
  it("asks the about endpoint once whether folders are offered", async () => {
    const fetcher = vi.fn(() => Promise.resolve(Response.json({ server_folders: true })));
    const folders = makeServerFolders(fetcher as unknown as typeof fetch);
    expect(await folders.available()).toBe(true);
    expect(await folders.available()).toBe(true);
    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  it("sends the folder chosen and gives back the inventory as text", async () => {
    const fetcher = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>(() =>
      Promise.resolve(Response.json(INVENTORY)),
    );
    const folders = makeServerFolders(fetcher as unknown as typeof fetch);
    expect(JSON.parse(await folders.describe("data", "cores"))).toEqual(INVENTORY);
    const [url, init] = fetcher.mock.calls[0] ?? [];
    expect(url).toBe("/api/folders/inventory");
    expect(JSON.parse(String(init?.body))).toEqual({
      root: "data",
      path: "cores",
    });
  });
});
