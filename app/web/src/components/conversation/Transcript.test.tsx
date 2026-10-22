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
    render(<Transcript conversation={withReply("**bold** and\n\n- one\n- two")} onOpenRun={() => {}} />);
    expect(screen.getAllByText("bold")[0]?.tagName).toBe("STRONG");
    expect(screen.getAllByRole("listitem").some((li) => li.textContent === "one")).toBe(true);
  });

  it("does not render raw HTML in a reply", () => {
    const { container } = render(
      <Transcript conversation={withReply("<img src=x onerror=alert(1)>")} onOpenRun={() => {}} />,
    );
    expect(container.querySelector("img")).toBeNull();
  });
});
