import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import type { DocumentationSummary } from "../../conversation/documentation";
import {
  httpProjectApi,
  ProjectApiContext,
  type ProjectApi,
} from "../../project/api";
import { AnnouncerProvider } from "../ui/Announcer";
import { AttachDocument, type OnAttached } from "./AttachDocument";

const HELD: DocumentationSummary = {
  documentation_name: "protocol.md",
  documentation_digest: "d1",
  documentation_media_type: "text/markdown",
  documentation_size: 42,
  documentation_added_at: "2026-11-10T10:00:00+00:00",
};

const NOTHING_FOUND = { findings: [], kinds: [], checked_with: "test" };

function renderAttach(
  api: Partial<ProjectApi>,
  onAttached: OnAttached = () => undefined,
) {
  const { container } = render(
    <ProjectApiContext.Provider
      value={{
        ...httpProjectApi,
        documentation: () => Promise.resolve([]),
        ...api,
      }}
    >
      <AnnouncerProvider>
        <AttachDocument
          projectId="p1"
          readers={{ readers: [], others: [] }}
          onAttached={onAttached}
        />
      </AnnouncerProvider>
    </ProjectApiContext.Provider>,
  );
  return container.querySelector<HTMLInputElement>(
    'input[type="file"]',
  ) as HTMLInputElement;
}

function markdown(text = "Cores were taken weekly.", name = "protocol.md") {
  return new File([text], name, { type: "text/markdown" });
}

describe("AttachDocument", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve(new Response(JSON.stringify(NOTHING_FOUND)))),
    );
  });
  afterEach(() => vi.unstubAllGlobals());

  it("keeps a chosen document in the project only once it is confirmed", async () => {
    const attachDocument = vi
      .fn<ProjectApi["attachDocument"]>()
      .mockResolvedValue([HELD]);
    const onAttached = vi.fn<OnAttached>();
    const input = renderAttach({ attachDocument }, onAttached);
    await userEvent.upload(input, markdown());
    const dialog = await screen.findByRole("dialog", {
      name: "Check the document before attaching it",
    });
    expect(attachDocument).not.toHaveBeenCalled();
    await userEvent.click(
      await within(dialog).findByRole("button", {
        name: "Attach this document",
      }),
    );
    await waitFor(() => expect(attachDocument).toHaveBeenCalledTimes(1));
    expect(attachDocument.mock.calls[0]?.[0]).toBe("p1");
    expect(attachDocument.mock.calls[0]?.[1]).toMatchObject({
      name: "protocol.md",
      media_type: "text/markdown",
      text: "Cores were taken weekly.",
    });
    expect(
      await screen.findByRole("log", { name: "Announcements" }),
    ).toHaveTextContent("protocol.md attached to the project.");
    expect(onAttached).toHaveBeenCalledWith([HELD], HELD);
  });

  it("keeps nothing when the check is cancelled", async () => {
    const attachDocument = vi.fn<ProjectApi["attachDocument"]>();
    const onAttached = vi.fn<OnAttached>();
    const input = renderAttach({ attachDocument }, onAttached);
    await userEvent.upload(input, markdown());
    const dialog = await screen.findByRole("dialog");
    await userEvent.click(
      within(dialog).getByRole("button", { name: /cancel|discard/i }),
    );
    expect(attachDocument).not.toHaveBeenCalled();
    expect(onAttached).not.toHaveBeenCalled();
  });

  it("says why a file that is not a document was not opened", async () => {
    const input = renderAttach({});
    await userEvent.upload(
      input,
      new File(["{}"], "inventory.json", { type: "application/json" }),
      { applyAccept: false },
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "inventory.json is not a document",
    );
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("closes the check and says why when the server refuses the document", async () => {
    const attachDocument = vi
      .fn<ProjectApi["attachDocument"]>()
      .mockRejectedValue(new Error("not kept"));
    const input = renderAttach({ attachDocument });
    await userEvent.upload(input, markdown());
    const dialog = await screen.findByRole("dialog");
    await userEvent.click(
      await within(dialog).findByRole("button", {
        name: "Attach this document",
      }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "The document was not attached",
    );
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
