import { render, screen, within } from "@testing-library/react";
import { axe } from "jest-axe";

import { StewardApiContext } from "../../project/steward";
import { ProjectViewProvider, useResearcherProject } from "../../project/view";
import { NO_STEWARDING } from "../../test/escalations";
import { MEMBER_VIEW, VIEW, fakeStewardApi } from "../../test/steward";
import { StewardConversationBanner } from "./StewardConversationBanner";
import { StewardRecord } from "./StewardRecord";

function AsksSteward() {
  return <output>{useResearcherProject(VIEW.project_id) ?? "none"}</output>;
}

function inProject(view: typeof VIEW) {
  return render(
    <StewardApiContext.Provider value={fakeStewardApi(view)}>
      <ProjectViewProvider projectId={VIEW.project_id}>
        <StewardConversationBanner />
        <AsksSteward />
      </ProjectViewProvider>
    </StewardApiContext.Provider>,
  );
}

describe("the conversation page in a project its steward opened", () => {
  it("says the runs act for the steward, and offers no request to a steward", async () => {
    const { container } = inProject(VIEW);
    const banner = await screen.findByRole("region", { name: /Working as a data steward/ });
    expect(within(banner).getByRole("link", { name: "Back to the project" })).toHaveAttribute(
      "href",
      `/projects/${VIEW.project_id}`,
    );
    expect(screen.getByRole("status")).toHaveTextContent("none");
    expect(await axe(container)).toHaveNoViolations();
  });

  it("shows a member no banner and keeps their offer to ask a steward", async () => {
    inProject(MEMBER_VIEW);
    expect(await screen.findByRole("status")).toHaveTextContent(VIEW.project_id);
    expect(screen.queryByRole("region", { name: /Working as a data steward/ })).not.toBeInTheDocument();
  });
});

describe("what data stewards did in a project, for its researchers", () => {
  it("lists each steward's reads and decisions on referred steps, the latest first", () => {
    const by = VIEW.created_by;
    render(
      <StewardRecord
        stewarding={{
          ...NO_STEWARDING,
          views: [{ by, at: "2026-01-01T09:00:00Z" }],
          gate_decisions: [
            { invocation_id: "r1", verdict: "refused", reason: "Not anonymised", by, at: "2026-01-02T09:00:00Z" },
          ],
        }}
      />,
    );
    const items = within(screen.getByRole("group")).getAllByRole("listitem");
    expect(items).toHaveLength(2);
    expect(items[0]).toHaveTextContent("Not anonymised");
  });

  it("shows nothing until a steward has done anything", () => {
    const { container } = render(<StewardRecord stewarding={NO_STEWARDING} />);
    expect(container).toBeEmptyDOMElement();
  });
});
