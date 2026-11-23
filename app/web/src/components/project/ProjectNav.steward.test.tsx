import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import type { ReactNode } from "react";

import { vi } from "vitest";

import { ActiveProjectTestContext } from "../../project/active";
import { EscalationsApiContext, type ProjectEscalations, type ProjectStewarding } from "../../project/escalations";
import { type StewardApi, StewardApiContext } from "../../project/steward";
import { ProjectViewProvider } from "../../project/view";
import { ESCALATIONS, NO_STEWARDING, fakeEscalationsApi } from "../../test/escalations";
import { MEMBER_VIEW, VIEW, fakeStewardApi } from "../../test/steward";
import { AnnouncerProvider } from "../ui/Announcer";
import { ProjectNav } from "./ProjectNav";

const PROJECT = VIEW.project_id;

function shown(api: StewardApi, children: ReactNode, escalations?: ProjectEscalations) {
  return render(
    <AnnouncerProvider>
      <EscalationsApiContext.Provider value={fakeEscalationsApi(escalations)}>
        <StewardApiContext.Provider value={api}>{children}</StewardApiContext.Provider>
      </EscalationsApiContext.Provider>
    </AnnouncerProvider>,
  );
}

describe("a project opened as its data steward", () => {
  const routed: ProjectEscalations = {
    ...ESCALATIONS,
    escalations: ESCALATIONS.escalations.map((e) => ({
      ...e,
      permitted_moves: [{ move: "take" as const, note: "none" as const, permitted: true }],
    })),
  };

  it("is marked as the steward's view, with the request beside it and no offer to ask a steward", async () => {
    const api = fakeStewardApi();
    const { container } = shown(
      api,
      <ProjectViewProvider projectId={PROJECT}>
        <ProjectNav projectId={PROJECT} name={VIEW.title} current="documents" />
      </ProjectViewProvider>,
      routed,
    );
    const banner = await screen.findByRole("region", { name: /Viewing as a data steward/ });
    expect(within(banner).getByRole("link", { name: /requests/ })).toHaveAttribute("href", "/steward");
    const requests = await screen.findByRole("list", { name: "Requests from this project" });
    expect(within(requests).getAllByRole("listitem").length).toBeGreaterThan(0);
    expect(screen.queryByRole("button", { name: "Ask a data steward" })).not.toBeInTheDocument();
    expect(await axe(container)).toHaveNoViolations();

    await userEvent.click(within(requests).getByRole("button", { name: /^Take/ }));
    const [first] = routed.escalations;
    expect(api.move).toHaveBeenCalledWith(PROJECT, first?.escalation_id, "take", undefined);
  });

  it("offers only the steps the harness permits, each with a note", async () => {
    const api = fakeStewardApi();
    shown(
      api,
      <ProjectViewProvider projectId={PROJECT}>
        <ProjectNav projectId={PROJECT} name={VIEW.title} current="documents" />
      </ProjectViewProvider>,
      routed,
    );
    await userEvent.click(await screen.findByRole("button", { name: "Pause the project" }));
    await userEvent.type(screen.getByRole("textbox", { name: /pausing/ }), "Checking consent forms");
    await userEvent.click(screen.getByRole("button", { name: "Pause the project" }));
    expect(api.step).toHaveBeenCalledWith(PROJECT, "pause", "Checking consent forms");
    expect(screen.queryByRole("button", { name: "Lift the pause" })).not.toBeInTheDocument();
  });

  it("shows a member no steward's banner", async () => {
    const api = fakeStewardApi(MEMBER_VIEW);
    shown(
      api,
      <ProjectViewProvider projectId={PROJECT}>
        <ProjectNav projectId={PROJECT} name={VIEW.title} current="documents" />
      </ProjectViewProvider>,
    );
    expect(await screen.findByRole("button", { name: "Ask a data steward" })).toBeInTheDocument();
    expect(api.view).toHaveBeenCalled();
    expect(screen.queryByRole("region", { name: /Viewing as a data steward/ })).not.toBeInTheDocument();
  });
});

describe("a steward's decision on a step referred to them", () => {
  const RUN = "019a0000-0000-7000-8000-0000000000r1";
  const [first] = ESCALATIONS.escalations;
  if (!first) throw new Error("no escalation in the fixture");
  const referred: ProjectEscalations = {
    ...ESCALATIONS,
    escalations: [
      {
        ...first,
        state: "taken",
        origin: { kind: "policy_gate", invocation_id: RUN },
        permitted_moves: [{ move: "resolve", note: "required", permitted: true }],
      },
    ],
  };

  function steward(api: StewardApi, stewarding: ProjectStewarding = NO_STEWARDING) {
    return render(
      <AnnouncerProvider>
        <EscalationsApiContext.Provider value={fakeEscalationsApi(referred, stewarding)}>
          <StewardApiContext.Provider value={api}>
            <ProjectViewProvider projectId={PROJECT}>
              <ProjectNav projectId={PROJECT} name={VIEW.title} current="documents" />
            </ProjectViewProvider>
          </StewardApiContext.Provider>
        </EscalationsApiContext.Provider>
      </AnnouncerProvider>,
    );
  }

  it("clears or refuses the step, each with a reason", async () => {
    const api = fakeStewardApi();
    const { container } = steward(api);
    expect(await screen.findByRole("link", { name: /Read the referred step/ })).toHaveAttribute(
      "href",
      `/?run=${RUN}`,
    );
    await userEvent.click(await screen.findByRole("button", { name: "Clear the step" }));
    await userEvent.type(screen.getByRole("textbox", { name: /clearing/ }), "Consent forms checked");
    expect(await axe(container)).toHaveNoViolations();
    await userEvent.click(screen.getByRole("button", { name: "Clear the step" }));
    expect(api.decideGate).toHaveBeenCalledWith(PROJECT, RUN, "cleared", "Consent forms checked");

    await userEvent.click(screen.getByRole("button", { name: "Refuse the step" }));
    await userEvent.type(screen.getByRole("textbox", { name: /refusing/ }), "Not anonymised");
    await userEvent.click(screen.getByRole("button", { name: "Refuse the step" }));
    expect(api.decideGate).toHaveBeenLastCalledWith(PROJECT, RUN, "refused", "Not anonymised");
  });

  it("shows a decision once made, and offers none again", async () => {
    const decided: ProjectStewarding = {
      ...NO_STEWARDING,
      gate_decisions: [
        { invocation_id: RUN, verdict: "cleared", reason: "Consent forms checked", by: first.opened_by, at: first.opened_at },
      ],
    };
    steward(fakeStewardApi(), decided);
    expect(await screen.findByText("Step cleared")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Clear the step" })).not.toBeInTheDocument();
  });

  it("asks an agent in the project, as the project the app works in", async () => {
    const setProjectId = vi.fn();
    render(
      <AnnouncerProvider>
        <ActiveProjectTestContext.Provider
          value={{ projectId: null, projects: [], setProjectId, reloadProjects: () => undefined }}
        >
          <EscalationsApiContext.Provider value={fakeEscalationsApi(referred)}>
            <StewardApiContext.Provider value={fakeStewardApi()}>
              <ProjectViewProvider projectId={PROJECT}>
                <ProjectNav projectId={PROJECT} name={VIEW.title} current="documents" />
              </ProjectViewProvider>
            </StewardApiContext.Provider>
          </EscalationsApiContext.Provider>
        </ActiveProjectTestContext.Provider>
      </AnnouncerProvider>,
    );
    await userEvent.click(await screen.findByRole("button", { name: "Ask an agent in this project" }));
    expect(setProjectId).toHaveBeenCalledWith(PROJECT);
    expect(window.location.pathname).toBe("/");
  });

  it("offers a member none of a steward's controls", async () => {
    steward(fakeStewardApi(MEMBER_VIEW));
    expect(await screen.findByRole("button", { name: "Ask a data steward" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Clear the step" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Ask an agent in this project" })).not.toBeInTheDocument();
  });
});
