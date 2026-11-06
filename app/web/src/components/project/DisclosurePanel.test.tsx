import { render, screen, within } from "@testing-library/react";
import { axe } from "jest-axe";

import fixture from "../../../fixtures/project-disclosure.json";
import { type Disclosure, type ProjectApi, ProjectApiContext } from "../../project/api";
import { DisclosurePanel, statementBody } from "./DisclosurePanel";

// What the server says (app/tests/test_document_decisions.py): a README a model drafted and a
// person approved as it stood, and a metadata record awaiting a decision.
const DISCLOSURE = fixture as Disclosure;

function renderPanel(api: Pick<ProjectApi, "disclosure">, revision = 0) {
  const full = { documents: vi.fn(), decide: vi.fn(), ...api } as unknown as ProjectApi;
  return render(
    <ProjectApiContext.Provider value={full}>
      <DisclosurePanel projectId={DISCLOSURE.project_id} revision={revision} />
    </ProjectApiContext.Provider>,
  );
}

describe("statementBody", () => {
  it("drops the statement's title and puts each document a level below the panel", () => {
    expect(statementBody("# Use of generative AI\n\nOne.\n\n## README\n\nTwo.\n")).toBe(
      "One.\n\n### README\n\nTwo.\n",
    );
  });
});

describe("DisclosurePanel", () => {
  it("shows the harness's statement and offers it and the PROV-O graph to download", async () => {
    const { container } = renderPanel({ disclosure: () => Promise.resolve(DISCLOSURE) });
    const panel = screen.getByRole("region", { name: "Use of generative AI" });
    expect(await within(panel).findByRole("heading", { name: "README", level: 3 })).toBeVisible();
    expect(within(panel).getByText(/reproduced verbatim/)).toBeVisible();
    expect(within(panel).getByText(/awaits a decision/)).toBeVisible();

    const statement = within(panel).getByRole("link", { name: "Download the statement" });
    expect(statement).toHaveAttribute("download", "use-of-generative-ai.md");
    expect(decodeURIComponent(statement.getAttribute("href") ?? "")).toContain(
      DISCLOSURE.statement,
    );
    const prov = within(panel).getByRole("link", { name: "Download the provenance (PROV-O)" });
    expect(prov).toHaveAttribute("download", "provenance.jsonld");
    expect(decodeURIComponent(prov.getAttribute("href") ?? "")).toContain(
      '"prov": "http://www.w3.org/ns/prov#"',
    );
    expect(await axe(container)).toHaveNoViolations();
  });

  it("reads the disclosure again when the project changes", async () => {
    const disclosure = vi.fn(() => Promise.resolve(DISCLOSURE));
    const { rerender } = renderPanel({ disclosure });
    await screen.findByRole("heading", { name: "README", level: 3 });
    rerender(
      <ProjectApiContext.Provider
        value={{ documents: vi.fn(), decide: vi.fn(), disclosure } as unknown as ProjectApi}
      >
        <DisclosurePanel projectId={DISCLOSURE.project_id} revision={1} />
      </ProjectApiContext.Provider>,
    );
    await vi.waitFor(() => expect(disclosure).toHaveBeenCalledTimes(2));
  });

  it("says when the disclosure cannot be read", async () => {
    renderPanel({ disclosure: () => Promise.reject(new Error("the server answered 500")) });
    expect(await screen.findByRole("alert")).toHaveTextContent("the server answered 500");
  });
});
