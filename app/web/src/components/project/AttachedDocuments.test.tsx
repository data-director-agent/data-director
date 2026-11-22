import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";

import type { DocumentationSummary } from "../../conversation/documentation";
import { httpProjectApi, ProjectApiContext, type ProjectApi } from "../../project/api";
import { type FactsApi, FactsApiContext } from "../../project/facts";
import { AnnouncerProvider } from "../ui/Announcer";
import { AttachedDocuments } from "./AttachedDocuments";

function held(name: string, digest: string, plan = false): DocumentationSummary {
  return {
    documentation_name: name,
    documentation_digest: digest,
    documentation_media_type: "text/plain",
    documentation_size: 42,
    documentation_added_at: "2026-11-10T10:00:00+00:00",
    ...(plan ? { documentation_is_plan: true } : {}),
  };
}

const EMPTY_FACTS = { proposals: [], decisions: [] };

function Listed({ initial }: { initial: DocumentationSummary[] }) {
  const [documents, setDocuments] = useState(initial);
  return <AttachedDocuments projectId="p1" held={documents} onChange={setDocuments} />;
}

function renderList(
  initial: DocumentationSummary[],
  after: DocumentationSummary[],
  decideFact: FactsApi["decideFact"],
) {
  const api: ProjectApi = { ...httpProjectApi, documentation: () => Promise.resolve(after) };
  const facts: FactsApi = { facts: () => Promise.resolve(EMPTY_FACTS), decideFact };
  render(
    <ProjectApiContext.Provider value={api}>
      <FactsApiContext.Provider value={facts}>
        <AnnouncerProvider>
          <Listed initial={initial} />
        </AnnouncerProvider>
      </FactsApiContext.Provider>
    </ProjectApiContext.Provider>,
  );
}

function item(name: string): HTMLElement {
  const list = screen.getByRole("region", { name: "Attached documents" });
  const found = within(list)
    .getAllByRole("listitem")
    .find((li) => li.textContent?.startsWith(name));
  if (!found) throw new Error(`no item ${name}`);
  return found;
}

describe("AttachedDocuments", () => {
  it("marks a document as the project's plan as a fact a person states", async () => {
    const decideFact = vi.fn<FactsApi["decideFact"]>().mockResolvedValue(EMPTY_FACTS);
    renderList(
      [held("notes.txt", "a"), held("dmp.docx", "b")],
      [held("notes.txt", "a"), held("dmp.docx", "b", true)],
      decideFact,
    );

    await userEvent.click(
      within(item("dmp.docx")).getByRole("button", { name: "Mark as the Data Management Plan" }),
    );

    await waitFor(() => expect(decideFact).toHaveBeenCalledTimes(1));
    expect(decideFact.mock.calls[0]?.[1]).toMatchObject({
      verdict: "changed",
      fact: { fact_kind: "data_management_plan", plan_document: "b" },
    });
    expect(await within(item("dmp.docx")).findByRole("button", { name: "Not the plan" })).toBeVisible();
    expect(within(item("notes.txt")).queryByRole("button", { name: "Not the plan" })).toBeNull();
  });

  it("removes the mark by rejecting the plan fact", async () => {
    const decideFact = vi.fn<FactsApi["decideFact"]>().mockResolvedValue(EMPTY_FACTS);
    renderList([held("dmp.docx", "b", true)], [held("dmp.docx", "b")], decideFact);

    await userEvent.click(within(item("dmp.docx")).getByRole("button", { name: "Not the plan" }));

    await waitFor(() => expect(decideFact).toHaveBeenCalledTimes(1));
    expect(decideFact.mock.calls[0]?.[1]).toMatchObject({
      verdict: "rejected",
      fact: { fact_kind: "data_management_plan" },
    });
    expect(
      await within(item("dmp.docx")).findByRole("button", { name: "Mark as the Data Management Plan" }),
    ).toBeVisible();
  });

  it("says nothing changed when the server refuses", async () => {
    const decideFact = vi.fn<FactsApi["decideFact"]>().mockRejectedValue(new Error("no"));
    renderList([held("dmp.docx", "b")], [held("dmp.docx", "b")], decideFact);

    await userEvent.click(
      within(item("dmp.docx")).getByRole("button", { name: "Mark as the Data Management Plan" }),
    );

    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});
