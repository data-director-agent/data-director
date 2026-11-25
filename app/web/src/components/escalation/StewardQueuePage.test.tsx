import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import type { ReactNode } from "react";

import { EscalationsApiContext, type ProjectEscalations } from "../../project/escalations";
import { type QueuedEscalation, type StewardApi, StewardApiContext } from "../../project/steward";
import { fakeEscalationsApi } from "../../test/escalations";
import { QUEUE, ROW, VIEW, fakeStewardApi } from "../../test/steward";
import { AnnouncerProvider } from "../ui/Announcer";
import { StewardQueuePage, ageSaid } from "./StewardQueuePage";


function shown(api: StewardApi, children: ReactNode, escalations?: ProjectEscalations) {
  return render(
    <AnnouncerProvider>
      <EscalationsApiContext.Provider value={fakeEscalationsApi(escalations)}>
        <StewardApiContext.Provider value={api}>{children}</StewardApiContext.Provider>
      </EscalationsApiContext.Provider>
    </AnnouncerProvider>,
  );
}

describe("a data steward's queue", () => {
  it("lists each request with its project, researcher, state and the moves the harness allows", async () => {
    const api = fakeStewardApi();
    const { container } = shown(api, <StewardQueuePage />);
    const table = await screen.findByRole("table");
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(QUEUE.length);
    const [row] = rows;
    if (!row) throw new Error("no row");
    expect(within(row).getByRole("link", { name: ROW.project_title ?? "" })).toHaveAttribute(
      "href",
      `/projects/${ROW.project_id}`,
    );
    expect(within(row).getByText(ROW.opened_by.name)).toBeInTheDocument();
    expect(api.queue).toHaveBeenCalledWith(["open", "taken", "waiting_for_researcher"], expect.anything());
    expect(await axe(container)).toHaveNoViolations();

    await userEvent.click(within(row).getByRole("button", { name: /^Take/ }));
    expect(api.move).toHaveBeenCalledWith(ROW.project_id, ROW.escalation_id, "take", undefined, undefined);
    expect(api.queue).toHaveBeenCalledTimes(2);
  });

  it("asks for a note before a move that needs one, and filters by state", async () => {
    const taken: QueuedEscalation = {
      ...ROW,
      state: "taken",
      permitted_moves: [{ move: "resolve", note: "required", permitted: true }],
    };
    const api = fakeStewardApi(VIEW, [taken]);
    shown(api, <StewardQueuePage />);
    await userEvent.click(await screen.findByRole("button", { name: /^Resolve/ }));
    await userEvent.type(screen.getByRole("textbox"), "Yes, once anonymised.");
    await userEvent.click(screen.getByRole("button", { name: /^Resolve/ }));
    expect(api.move).toHaveBeenCalledWith(
      ROW.project_id,
      ROW.escalation_id,
      "resolve",
      "Yes, once anonymised.",
      undefined,
    );

    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Show" }), "resolved");
    expect(api.queue).toHaveBeenLastCalledWith(["resolved"], expect.anything());
  });

  it("passes a taken request to a colleague the harness lists", async () => {
    const taken: QueuedEscalation = {
      ...ROW,
      state: "taken",
      permitted_moves: [
        {
          move: "reassign",
          note: "optional",
          permitted: true,
          targets: [
            { id: "https://orcid.org/0000-0003-1415-9269", name: "Grace Example" },
            { id: "https://orcid.org/0000-0001-5109-3700", name: "Alan Example" },
          ],
        },
      ],
    };
    const api = fakeStewardApi(VIEW, [taken]);
    const { container } = shown(api, <StewardQueuePage />);
    await userEvent.click(await screen.findByRole("button", { name: /^Reassign/ }));
    const colleague = screen.getByRole("combobox", { name: /Colleague/ });
    expect(within(colleague).getAllByRole("option")).toHaveLength(2);
    await userEvent.selectOptions(colleague, "https://orcid.org/0000-0001-5109-3700");
    expect(await axe(container)).toHaveNoViolations();
    await userEvent.click(screen.getByRole("button", { name: /^Reassign/ }));
    expect(api.move).toHaveBeenCalledWith(
      ROW.project_id,
      ROW.escalation_id,
      "reassign",
      undefined,
      "https://orcid.org/0000-0001-5109-3700",
    );
  });

  it("transfers a request to another team, with the note it needs", async () => {
    const open: QueuedEscalation = {
      ...ROW,
      permitted_moves: [
        {
          move: "transfer",
          note: "required",
          permitted: true,
          targets: [{ id: "faculty", name: "Faculty Data Team" }],
        },
      ],
    };
    const api = fakeStewardApi(VIEW, [open]);
    shown(api, <StewardQueuePage />);
    await userEvent.click(await screen.findByRole("button", { name: /^Transfer/ }));
    expect(screen.getByRole("combobox", { name: /Team/ })).toHaveValue("faculty");
    await userEvent.click(screen.getByRole("button", { name: /^Transfer/ }));
    expect(api.move).not.toHaveBeenCalled();
    await userEvent.type(screen.getByRole("textbox"), "A matter for the faculty.");
    await userEvent.click(screen.getByRole("button", { name: /^Transfer/ }));
    expect(api.move).toHaveBeenCalledWith(
      ROW.project_id,
      ROW.escalation_id,
      "transfer",
      "A matter for the faculty.",
      "faculty",
    );
  });

  it("says why a move is refused, rather than hiding it", async () => {
    const member: QueuedEscalation = {
      ...ROW,
      member_of_project: true,
      permitted_moves: [{ move: "take", note: "none", permitted: false, refusal: "member-of-project" }],
    };
    shown(fakeStewardApi(VIEW, [member]), <StewardQueuePage />);
    const table = await screen.findByRole("table");
    expect(within(table).queryByRole("button", { name: /^Take/ })).not.toBeInTheDocument();
    expect(within(table).getByText(/member of this project/)).toBeInTheDocument();
  });

  it("says a request's age in whole days", () => {
    const now = Date.parse("2026-01-03T12:00:00Z");
    expect(ageSaid("2026-01-03T09:00:00Z", now)).toBe("Today");
    expect(ageSaid("2026-01-01T09:00:00Z", now)).toMatch(/^2/);
  });
});
