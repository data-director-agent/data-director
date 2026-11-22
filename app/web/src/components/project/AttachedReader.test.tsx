import { render, screen, within } from "@testing-library/react";

import type { DocumentationSummary } from "../../conversation/documentation";
import { ProjectApiContext } from "../../project/api";
import { fakeProjectApi } from "../../test/projectApi";
import { AnnouncerProvider } from "../ui/Announcer";
import { AttachedReader } from "./AttachedReader";

const NOTES: DocumentationSummary = {
  documentation_name: "protocol.md",
  documentation_digest: "b".repeat(64),
  documentation_media_type: "text/markdown",
  documentation_size: 64,
  documentation_added_at: "2026-11-10T10:00:00Z",
};

describe("AttachedReader", () => {
  it("lays out a document attached as text, with nothing to download", async () => {
    const text = "# Protocol\n\n- weekly\n- at 10 cm\n";
    render(
      <ProjectApiContext.Provider
        value={fakeProjectApi({
          documentationText: () =>
            Promise.resolve({ text, mediaType: "text/markdown" }),
        })}
      >
        <AnnouncerProvider>
          <AttachedReader
            projectId="p1"
            document={NOTES}
            onChange={() => undefined}
          />
        </AnnouncerProvider>
      </ProjectApiContext.Provider>,
    );
    const article = await screen.findByRole("article", {
      name: NOTES.documentation_name,
    });
    expect(
      await within(article).findByRole("heading", { name: "Protocol" }),
    ).toBeVisible();
    expect(within(article).getAllByRole("listitem").length).toBeGreaterThan(0);
    expect(within(article).getByRole("tablist")).toBeVisible();
    expect(
      within(article).queryByRole("link", { name: /Download/ }),
    ).toBeNull();
  });
});
