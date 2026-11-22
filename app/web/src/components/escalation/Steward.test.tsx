import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import type { ReactNode } from "react";

import type { Question } from "../../conversation/question";
import { EscalationsApiContext, type EscalationsApi, type ProjectEscalations } from "../../project/escalations";
import type { Envelope } from "../../run/types";
import { ESCALATIONS, NONE_YET, NO_STEWARDING, fakeEscalationsApi } from "../../test/escalations";
import { shortlistRun } from "../../test/shortlist";
import { AnnouncerProvider } from "../ui/Announcer";
import { StewardProvider } from "./StewardContext";
import { StewardItems } from "./StewardItems";
import { RunStewardOffer, STEWARD_KEY, StewardOfferQuestion } from "./StewardOffer";
import { StewardSection } from "./StewardSection";

const PROJECT = "019a0000-0000-7000-8000-0000000000p1";
const [OPEN] = ESCALATIONS.escalations;
if (!OPEN) throw new Error("no escalation in the fixture");

function inProject(api: EscalationsApi, children: ReactNode) {
  return render(
    <AnnouncerProvider>
      <EscalationsApiContext.Provider value={api}>
        <StewardProvider projectId={PROJECT} project={{ title: "Moorland birds" }}>
          {children}
        </StewardProvider>
      </EscalationsApiContext.Provider>
    </AnnouncerProvider>,
  );
}

function referred(reason_code: string): Envelope {
  return shortlistRun({
    invocation_id: "019a0000-0000-7000-8000-0000000000r1",
    outcome: { status: "referred", statement: "Needs a person.", reason_code },
  });
}

async function ask() {
  const button = await screen.findByRole("button", { name: "Ask a data steward" });
  await waitFor(() => expect(button).toBeEnabled());
  await userEvent.click(button);
  return screen.findByRole("dialog", { name: "Ask a data steward" });
}

describe("asking a data steward", () => {
  it("sends the researcher's note with what they saw would be shared, only once they confirm", async () => {
    const api = fakeEscalationsApi();
    const { container } = inProject(api, <StewardSection />);
    const dialog = await ask();
    expect(api.open).not.toHaveBeenCalled();
    const shared = within(dialog).getByRole("group", { name: "What will be shared" });
    const lines = within(shared).getAllByRole("checkbox");
    expect(lines.length).toBeGreaterThan(0);
    const [untick] = lines;
    if (!untick) throw new Error("no line shared");
    await userEvent.click(untick);
    await userEvent.type(within(dialog).getByRole("textbox"), "Can I share these recordings?");
    await userEvent.click(within(dialog).getByRole("button", { name: "Send to a data steward" }));

    expect(api.open).toHaveBeenCalledTimes(1);
    const [projectId, sent] = api.open.mock.calls[0] ?? [];
    expect(projectId).toBe(PROJECT);
    expect(sent?.origin).toEqual({ kind: "researcher" });
    expect(sent?.note).toBe("Can I share these recordings?");
    expect(sent?.scope_shared).toHaveLength(lines.length - 1);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("says there is no steward team instead of offering to send", async () => {
    const none: ProjectEscalations = { ...NONE_YET, teams: [], routes_to: null, unrouted: "no-steward-team" };
    inProject(fakeEscalationsApi(none), <StewardSection />);
    const section = await screen.findByRole("region", { name: "Data steward" });
    expect(await within(section).findByText(/No data steward team/)).toBeInTheDocument();
    expect(within(section).queryByRole("button", { name: "Ask a data steward" })).not.toBeInTheDocument();
  });

  it("asks which team when the project has none and the deployment several", async () => {
    const second = { ...ESCALATIONS.teams[0], team_id: "it-security", name: "IT Security", supports: [] };
    const several: ProjectEscalations = {
      ...NONE_YET,
      teams: [...ESCALATIONS.teams, second],
      routes_to: null,
      unrouted: "team-required",
    };
    const api = fakeEscalationsApi(several);
    inProject(api, <StewardSection />);
    const dialog = await ask();
    await userEvent.type(within(dialog).getByRole("textbox"), "Help");
    const teams = within(dialog).getByRole("group", { name: "Which data steward team?" });
    await userEvent.click(within(dialog).getByRole("button", { name: "Send to a data steward" }));
    expect(api.open).not.toHaveBeenCalled();
    expect(within(dialog).getByRole("alert")).toBeInTheDocument();

    await userEvent.click(within(teams).getByRole("radio", { name: "IT Security" }));
    await userEvent.click(within(dialog).getByRole("button", { name: "Send to a data steward" }));
    expect(api.open.mock.calls[0]?.[1].team_id).toBe("it-security");
  });
});

describe("a request already sent", () => {
  it("shows its status, and withdraws it without a note", async () => {
    const api = fakeEscalationsApi(ESCALATIONS);
    inProject(api, <StewardSection />);
    const list = await screen.findByRole("list", { name: "Requests to a data steward" });
    const [row] = within(list).getAllByRole("listitem");
    if (!row) throw new Error("no request listed");
    expect(within(row).getByText(OPEN.team_name, { exact: false })).toBeInTheDocument();
    await userEvent.click(within(row).getByRole("button", { name: /Withdraw/ }));
    expect(api.move).toHaveBeenCalledWith(PROJECT, OPEN.escalation_id, "withdraw", undefined);
  });

  it("asks for a note before replying to a steward who is waiting", async () => {
    const waiting: ProjectEscalations = {
      ...ESCALATIONS,
      escalations: [{ ...OPEN, state: "waiting_for_researcher" }],
    };
    const api = fakeEscalationsApi(waiting);
    inProject(api, <StewardSection />);
    await userEvent.click(await screen.findByRole("button", { name: "Reply" }));
    await userEvent.type(screen.getByRole("textbox", { name: /reply/ }), "It is anonymised.");
    await userEvent.click(screen.getByRole("button", { name: "Reply" }));
    expect(api.move).toHaveBeenCalledWith(PROJECT, OPEN.escalation_id, "reply", "It is anonymised.");
  });

  it("shows a steward's message in the conversation as from a named person, not an agent", async () => {
    const stewarding = {
      ...NO_STEWARDING,
      messages: [{ at: "2026-01-02T00:00:00+00:00", by: { ...OPEN.opened_by, name: "Ada Steward" }, note: "Looks fine." }],
    };
    inProject(
      fakeEscalationsApi(ESCALATIONS, stewarding),
      <ol aria-label="Conversation">
        <StewardItems from="2026-01-01T12:00:00+00:00" to={null} />
      </ol>,
    );
    const list = screen.getByRole("list", { name: "Conversation" });
    expect(await within(list).findByText(/Data steward: Ada Steward/)).toBeInTheDocument();
    expect(within(list).getByText("Looks fine.")).toBeInTheDocument();
    // The researcher's own request, opened before `from`, is not repeated here.
    expect(within(list).getAllByRole("listitem")).toHaveLength(1);
  });
});

describe("offers from a run", () => {
  it("offers a step stopped for approval with no 'Not now', from the policy gate", async () => {
    const api = fakeEscalationsApi();
    const run = referred("policy_requires_approval");
    inProject(api, <RunStewardOffer envelope={run} />);
    const dialog = await ask();
    expect(within(dialog).queryByRole("button", { name: "Not now" })).not.toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Leave it stopped" })).toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole("button", { name: "Send to a data steward" }));
    expect(api.open.mock.calls[0]?.[1].origin).toEqual({ kind: "policy_gate", invocation_id: run.invocation_id });
  });

  it("offers nothing for a run that succeeded, or one already sent", async () => {
    const run = referred("requires_human_judgement");
    const sent: ProjectEscalations = {
      ...ESCALATIONS,
      escalations: [{ ...OPEN, origin: { kind: "agent", invocation_id: run.invocation_id } }],
    };
    inProject(
      fakeEscalationsApi(sent),
      <>
        <RunStewardOffer envelope={shortlistRun()} />
        <RunStewardOffer envelope={run} />
      </>,
    );
    expect(await screen.findByText(new RegExp(OPEN.team_name))).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Ask a data steward" })).not.toBeInTheDocument();
  });
});

describe("the orchestrator's offer", () => {
  const question: Question = {
    question_key: STEWARD_KEY,
    question_prompt: "Would you like to ask a data steward?",
    question_kind: "choice",
    question_options: [
      { option_value: "send", option_label: "Ask a data steward" },
      { option_value: "not-now", option_label: "Not now" },
    ],
  };
  const turn = "019a0000-0000-7000-8000-0000000000t1";

  it("answers 'not now' without sending anything", async () => {
    const api = fakeEscalationsApi();
    const onAnswer = vi.fn();
    inProject(api, <StewardOfferQuestion question={question} askedBy={turn} onAnswer={onAnswer} disabled={false} />);
    await userEvent.click(await screen.findByRole("button", { name: "Not now" }));
    expect(api.open).not.toHaveBeenCalled();
    expect(onAnswer.mock.calls[0]?.[0].given_answers).toEqual([{ answered_key: STEWARD_KEY, answer_values: ["not-now"] }]);
  });

  it("sends from the orchestrator's turn, and answers once it is sent", async () => {
    const api = fakeEscalationsApi();
    const onAnswer = vi.fn();
    inProject(api, <StewardOfferQuestion question={question} askedBy={turn} onAnswer={onAnswer} disabled={false} />);
    const dialog = await ask();
    expect(onAnswer).not.toHaveBeenCalled();
    await userEvent.type(within(dialog).getByRole("textbox"), "Help with consent");
    await userEvent.click(within(dialog).getByRole("button", { name: "Send to a data steward" }));
    expect(api.open.mock.calls[0]?.[1].origin).toEqual({ kind: "orchestrator", invocation_id: turn });
    expect(onAnswer.mock.calls[0]?.[0].given_answers).toEqual([{ answered_key: STEWARD_KEY, answer_values: ["send"] }]);
  });
});
