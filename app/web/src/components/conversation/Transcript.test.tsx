import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import conversationFixture from "../../../fixtures/conversation.json";
import type { Conversation } from "../../conversation/types";
import { Transcript } from "./Transcript";

function withReply(text: string): Conversation {
  const conversation = structuredClone(conversationFixture) as unknown as Conversation;
  for (const entry of conversation.history) {
    if (entry.role === "agent") entry.turn_text = text;
  }
  return conversation;
}

describe("Transcript", () => {
  it("renders Markdown in a reply as formatted text", () => {
    render(<Transcript conversation={withReply("**bold** and\n\n- one\n- two")} agents={[]} onToggleRun={() => {}} />);
    expect(screen.getAllByText("bold")[0]?.tagName).toBe("STRONG");
    expect(screen.getAllByRole("listitem").some((li) => li.textContent === "one")).toBe(true);
  });

  it("does not render raw HTML in a reply", () => {
    const { container } = render(
      <Transcript conversation={withReply("<img src=x onerror=alert(1)>")} agents={[]} onToggleRun={() => {}} />,
    );
    expect(container.querySelector("img")).toBeNull();
  });

  it("shows the project's inventory as a chip on the turn it was given, not after", () => {
    const conversation = structuredClone(conversationFixture) as unknown as Conversation;
    const summary = {
      inventory_digest: "a".repeat(64),
      inventory_file_count: 42,
      inventory_tool: "dd-inventory",
      inventory_tool_version: "0.1.0",
      inventory_made_at: "2026-11-01T09:00:00Z",
    };
    for (const turn of conversation.turns) {
      const input = conversation.inputs[turn.invocation_id];
      if (input) input.project_inventory = summary;
    }
    expect(conversation.turns.length).toBeGreaterThan(1);
    render(<Transcript conversation={conversation} agents={[]} onToggleRun={() => {}} />);
    expect(screen.getAllByText("Inventory: 42 files, made 1 Nov 2026")).toHaveLength(1);
  });
});
