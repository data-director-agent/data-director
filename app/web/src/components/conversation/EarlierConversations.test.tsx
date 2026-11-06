import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import type { ConversationSummary } from "../../conversation/types";
import { EarlierConversations } from "./EarlierConversations";

function summary(over: Partial<ConversationSummary>): ConversationSummary {
  return {
    conversation_id: "c1",
    agent_id: "orchestrator.model",
    title: "Depositing a soil survey",
    title_source: "model",
    turns: 1,
    started_at: "2026-01-01T09:30:00Z",
    ...over,
  };
}

describe("EarlierConversations", () => {
  it("names each conversation by its title, with the date and turns kept in its name", async () => {
    const onOpen = vi.fn();
    const { container } = render(
      <EarlierConversations
        conversations={[
          summary({ conversation_id: "c1", turns: 1 }),
          summary({ conversation_id: "c2", started_at: "2026-02-03T14:00:00Z", turns: 3 }),
        ]}
        onOpen={onOpen}
      />,
    );
    const buttons = screen.getAllByRole("button", { name: /^Depositing a soil survey / });
    expect(buttons).toHaveLength(2);
    // The same title twice, told apart by the date and turns in the accessible name.
    const [first, second] = buttons as [HTMLElement, HTMLElement];
    expect(first).toHaveAccessibleName(/, 1 turn$/);
    expect(second).toHaveAccessibleName(/, 3 turns$/);
    expect(second.querySelector("time")).toHaveAttribute("dateTime", "2026-02-03T14:00:00Z");

    await userEvent.click(second);
    expect(onOpen).toHaveBeenCalledWith("c2");
    expect(await axe(container)).toHaveNoViolations();
  });

  it("shows a title taken from the first message like any other", () => {
    render(
      <EarlierConversations
        conversations={[summary({ title: "Which licence should I use?", title_source: "message" })]}
        onOpen={() => undefined}
      />,
    );
    expect(screen.getByText("Which licence should I use?")).toBeVisible();
  });

  it("says there are none yet, and still offers a new conversation", async () => {
    const onNew = vi.fn();
    render(<EarlierConversations conversations={[]} onOpen={() => undefined} onNew={onNew} />);
    expect(screen.getByText("No conversations yet.")).toBeVisible();
    await userEvent.click(screen.getByRole("button", { name: "New conversation" }));
    expect(onNew).toHaveBeenCalled();
  });

  it("marks the open conversation as current", () => {
    render(
      <EarlierConversations
        conversations={[summary({ conversation_id: "c1" }), summary({ conversation_id: "c2", turns: 3 })]}
        currentId="c2"
        onOpen={() => undefined}
      />,
    );
    expect(screen.getByRole("button", { name: /, 3 turns$/ })).toHaveAttribute("aria-current", "true");
    expect(screen.getByRole("button", { name: /, 1 turn$/ })).not.toHaveAttribute("aria-current");
  });
});
