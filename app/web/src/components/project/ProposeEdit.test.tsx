import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { vi } from "vitest";

import { type ProjectApi, ProjectApiContext, digestOf } from "../../project/api";
import { type ProjectView, type StewardApi, StewardApiContext } from "../../project/steward";
import { ProjectViewProvider } from "../../project/view";
import { DRAFT, PROJECT, fakeProjectApi } from "../../test/projectApi";
import { MEMBER_VIEW, VIEW, fakeStewardApi } from "../../test/steward";
import { AnnouncerProvider } from "../ui/Announcer";
import { ProjectPage } from "./ProjectPage";

function opened(view: ProjectView, steward: StewardApi = fakeStewardApi(view), api: ProjectApi = fakeProjectApi()) {
  return render(
    <ProjectApiContext.Provider value={api}>
      <StewardApiContext.Provider value={steward}>
        <AnnouncerProvider>
          <ProjectViewProvider projectId={PROJECT.project_id}>
            <ProjectPage projectId={PROJECT.project_id} query={`doc=${DRAFT.document_id}`} />
          </ProjectViewProvider>
        </AnnouncerProvider>
      </StewardApiContext.Provider>
    </ProjectApiContext.Provider>,
  );
}

describe("a data steward's edit to a document", () => {
  it("proposes the steward's version of the latest one, for the owners to decide", async () => {
    const steward = fakeStewardApi(VIEW);
    const documents = vi.fn(() => Promise.resolve(PROJECT));
    const { container } = opened(VIEW, steward, fakeProjectApi({ documents }));
    const article = await screen.findByRole("article", { name: "README" });
    await userEvent.click(await within(article).findByRole("button", { name: /^Propose an edit/ }));
    const form = within(article).getByRole("form", { name: "Propose an edit" });
    const text = within(form).getByLabelText("Your version of the text");
    expect(text).toHaveValue(DRAFT.text);
    await userEvent.type(text, " Edited.");
    expect(await axe(container)).toHaveNoViolations();
    const reads = documents.mock.calls.length;
    await userEvent.click(within(form).getByRole("button", { name: "Propose this version" }));

    expect(steward.proposeEdit).toHaveBeenCalledWith(PROJECT.project_id, DRAFT.document_id, {
      version: DRAFT.version,
      digest: digestOf(DRAFT.text),
      text: `${DRAFT.text} Edited.`,
    });
    expect(documents.mock.calls.length).toBeGreaterThan(reads);
  });

  it("offers a steward no decision on it, and a member no steward's edit", async () => {
    opened(VIEW);
    const article = await screen.findByRole("article", { name: "README" });
    await within(article).findByRole("button", { name: /^Propose an edit/ });
    expect(within(article).queryByRole("radio")).not.toBeInTheDocument();

    document.body.innerHTML = "";
    opened(MEMBER_VIEW);
    const theirs = await screen.findByRole("article", { name: "README" });
    expect(within(theirs).queryByRole("button", { name: /^Propose an edit/ })).not.toBeInTheDocument();
  });
});
