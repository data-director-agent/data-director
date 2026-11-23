import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import type { ReactNode } from "react";
import { type Mock, vi } from "vitest";

import queueFixture from "../../../fixtures/steward-queue.json";
import viewFixture from "../../../fixtures/project-steward-view.json";
import { EscalationsApiContext, type ProjectEscalations } from "../../project/escalations";
import {
  type ProjectView,
  type QueuedEscalation,
  type StewardApi,
  StewardApiContext,
} from "../../project/steward";
import { ProjectViewProvider } from "../../project/view";
import { ESCALATIONS, fakeEscalationsApi } from "../../test/escalations";
import { AnnouncerProvider } from "../ui/Announcer";
import { ProjectNav } from "./ProjectNav";

const QUEUE = queueFixture.escalations as QueuedEscalation[];
function firstOf(queue: QueuedEscalation[]): QueuedEscalation {
  const [row] = queue;
  if (!row) throw new Error("no escalation in the fixture");
  return row;
}
const ROW = firstOf(QUEUE);
const VIEW = viewFixture as ProjectView;
const PROJECT = VIEW.project_id;

function fakeStewardApi(view: ProjectView = VIEW, queue: QueuedEscalation[] = QUEUE) {
  return {
    queue: vi.fn<StewardApi["queue"]>(() => Promise.resolve(queue)),
    move: vi.fn<StewardApi["move"]>(() => Promise.resolve({ ...ROW, state: "taken" })),
    view: vi.fn<StewardApi["view"]>(() => Promise.resolve(view)),
    step: vi.fn<StewardApi["step"]>(() => Promise.resolve()),
  } satisfies Record<keyof StewardApi, Mock>;
}

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
    const member: ProjectView = { ...VIEW, permitted_actions: { acting_as: "member", actions: [] } };
    const api = fakeStewardApi(member);
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
