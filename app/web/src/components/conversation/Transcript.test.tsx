import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import conversationFixture from "../../../fixtures/conversation.json";
import projectFixture from "../../../fixtures/project-documents.json";
import type { Conversation } from "../../conversation/types";
import type { DocumentVersion, ProjectDocument, ProjectDocuments } from "../../project/api";
import { Transcript } from "./Transcript";

/** The fixture's README, drafted by `invocationId`, with `later` versions after it. */
function readmeDraftedBy(invocationId: string, later: DocumentVersion[] = []): ProjectDocument {
  const readme = (projectFixture as ProjectDocuments).documents[0] as ProjectDocument;
  const draft = readme.versions[0] as DocumentVersion;
  const drafter = draft.drafted_by as NonNullable<DocumentVersion["drafted_by"]>;
  return { ...readme, versions: [{ ...draft, drafted_by: { ...drafter, invocation_id: invocationId } }, ...later] };
}

function withReply(text: string): Conversation {
  const conversation = structuredClone(conversationFixture) as unknown as Conversation;
  for (const entry of conversation.history) {
    if (entry.role === "agent") entry.turn_text = text;
  }
  for (const turn of conversation.turns) {
    if (turn.envelope.payload) turn.envelope.payload.reply_text = text;
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
    const { rerender } = render(<Transcript conversation={conversation} agents={[]} onToggleRun={() => {}} />);
    expect(screen.getAllByText("Inventory: 42 files, made 1 Nov 2026")).toHaveLength(1);

    // Only the inventory the project holds now is served, so only its chip opens it.
    const project = { project_id: "p1", inventory: null };
    const replaced = { digest: "b".repeat(64), file_count: 1, inventory_made_at: "x", added_at: "x" };
    rerender(
      <Transcript conversation={{ ...conversation, ...project, inventory: replaced }} agents={[]} onToggleRun={() => {}} />,
    );
    expect(screen.queryByRole("button", { name: "View inventory" })).toBeNull();
    const current = { ...replaced, digest: summary.inventory_digest };
    rerender(
      <Transcript conversation={{ ...conversation, ...project, inventory: current }} agents={[]} onToggleRun={() => {}} />,
    );
    expect(screen.getByRole("button", { name: "View inventory" })).toBeVisible();
  });

  it("shows each attached document as a chip on the turn it was given, never its text", () => {
    const conversation = structuredClone(conversationFixture) as unknown as Conversation;
    const protocol = {
      documentation_name: "protocol.md",
      documentation_digest: "c".repeat(64),
      documentation_media_type: "text/markdown",
      documentation_size: 2048,
      documentation_added_at: "2026-11-01T09:00:00Z",
    };
    const codebook = { ...protocol, documentation_name: "codebook.txt", documentation_digest: "d".repeat(64) };
    const [first, second] = conversation.turns;
    if (!first || !second) throw new Error("the fixture has fewer than two turns");
    const at = (id: string) => conversation.inputs[id] as NonNullable<Conversation["inputs"][string]>;
    at(first.invocation_id).project_documentation = [protocol];
    at(second.invocation_id).project_documentation = [protocol, codebook];
    render(<Transcript conversation={conversation} agents={[]} onToggleRun={() => {}} />);
    expect(screen.getAllByText(/Document: protocol.md/)).toHaveLength(1);
    expect(screen.getAllByText(/Document: codebook.txt/)).toHaveLength(1);
    expect(screen.getAllByText("(2.0 KB)")).toHaveLength(2);
  });

  describe("a document drafted on a turn", () => {
    const conversation = structuredClone(conversationFixture) as unknown as Conversation;
    const first = conversation.turns[0];
    const child = first?.children[0];
    if (!first || !child) throw new Error("the fixture's first turn delegates to no agent");
    const projectId = conversation.project_id ?? "";

    it("is a card on the turn whose delegated run drafted it, before that run", async () => {
      render(
        <Transcript
          conversation={conversation}
          agents={[]}
          onToggleRun={() => {}}
          documents={[readmeDraftedBy(child.invocation_id)]}
        />,
      );
      const lists = screen.getAllByRole("list", { name: "Documents drafted on this turn" });
      expect(lists).toHaveLength(1);
      const card = within(lists[0] as HTMLElement).getByRole("listitem");
      expect(card).toHaveTextContent("README, version 1");
      expect(within(card).getByText("Proposed, not reviewed")).toBeVisible();
      expect(within(card).getByRole("link", { name: "Review and approve README" })).toHaveAttribute(
        "href",
        `/projects/${projectId}?doc=${readmeDraftedBy("x").document_id}`,
      );
      // The card comes before the delegated runs that are its evidence.
      const runs = screen.getAllByRole("list", { name: /delegated to/ })[0] as HTMLElement;
      expect(lists[0]?.compareDocumentPosition(runs)).toBe(Node.DOCUMENT_POSITION_FOLLOWING);

      // The preview is closed at first, and opens to the text with copy and download.
      const preview = within(card).getByRole("button", { name: "Preview of README, version 1" });
      expect(preview).toHaveAttribute("aria-expanded", "false");
      expect(within(card).queryByRole("heading", { name: "README" })).toBeNull();
      await userEvent.click(preview);
      expect(preview).toHaveAttribute("aria-expanded", "true");
      expect(within(card).getByRole("heading", { name: "README" })).toBeVisible();
      expect(within(card).getByRole("heading", { name: "Untitled dataset" })).toBeVisible();
      expect(within(card).getByRole("link", { name: /Download readme\.md/ })).toBeVisible();
      await userEvent.click(preview);
      expect(within(card).queryByRole("heading", { name: "README" })).toBeNull();
    });

    it("says when a later version has replaced the draft, and links to it to open", () => {
      const draft = readmeDraftedBy(child.invocation_id).versions[0] as DocumentVersion;
      const edit: DocumentVersion = { ...draft, version: 2, drafted_by: null, state: "approved" };
      render(
        <Transcript
          conversation={conversation}
          agents={[]}
          onToggleRun={() => {}}
          documents={[readmeDraftedBy(child.invocation_id, [edit])]}
        />,
      );
      const card = screen.getByRole("list", { name: "Documents drafted on this turn" });
      expect(card).toHaveTextContent("Version 2 is now the latest.");
      expect(within(card).getByRole("link", { name: "Open in the project's documents README" })).toBeVisible();
    });

    it("shows no card for a run that drafted no project document, or before the documents are read", () => {
      const { rerender } = render(
        <Transcript conversation={conversation} agents={[]} onToggleRun={() => {}} documents={[readmeDraftedBy("elsewhere")]} />,
      );
      expect(screen.queryByRole("list", { name: "Documents drafted on this turn" })).toBeNull();
      rerender(<Transcript conversation={conversation} agents={[]} onToggleRun={() => {}} documents={null} />);
      expect(screen.queryByRole("list", { name: "Documents drafted on this turn" })).toBeNull();
    });
  });
});
