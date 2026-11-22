import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { describe, expect, it, vi } from "vitest";

import { DEFAULT_AGENT_ICON } from "@data-director/agent-view";

import several from "../../../fixtures/agents-several.json";
import conversationFixture from "../../../fixtures/conversation.json";
import projectFixture from "../../../fixtures/project-documents.json";
import projectsFixture from "../../../fixtures/projects.json";
import runFixture from "../../../fixtures/run-succeeded.json";
import type { Conversation } from "../../conversation/types";
import { normalise } from "../../manifest/normalise";
import type { RawAgentsResponse } from "../../manifest/types";
import type {
  DocumentVersion,
  ProjectDocument,
  ProjectDocuments,
  ProjectSummary,
} from "../../project/api";
import { projectName } from "../../project/name";
import { type RunApi, RunApiContext } from "../../run/api";
import type { RunResult } from "../../run/types";
import { savedInventory } from "../../test/api";
import { SessionApiContext } from "../../session/api";
import { DEVELOPMENT, fakeSessionApi } from "../../test/session";
import { Transcript } from "./Transcript";

const COLLEAGUE = "https://orcid.org/0000-0001-5000-0007";

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
  it("says a failed reply plainly, keeps the agent's text for operators and offers to try again", async () => {
    const conversation = structuredClone(conversationFixture) as unknown as Conversation;
    const last = conversation.turns[conversation.turns.length - 1];
    if (!last) throw new Error("the fixture has no turn");
    const error = "ModelError: the Messages API answered 502 'provider-error'";
    last.envelope.payload = null;
    last.envelope.outcome = { ...last.envelope.outcome, status: "failed", statement: error };
    for (const entry of conversation.history) {
      if (entry.turn_invocation_id === last.invocation_id) entry.turn_text = error;
    }
    const onRetry = vi.fn();
    render(<Transcript conversation={conversation} agents={[]} onToggleRun={() => {}} onRetry={onRetry} />);

    const disclosure = screen.getByText(/whoever runs Data Director$/).closest("details");
    expect(disclosure).not.toBeNull();
    expect(disclosure).not.toHaveAttribute("open");
    expect(screen.getAllByText(error, { exact: false }).every((e) => disclosure?.contains(e))).toBe(true);
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(onRetry).toHaveBeenCalledWith(conversation.inputs[last.invocation_id]?.message_text ?? "");
  });

  it("shows a message that sends answers as Markdown, and a typed one as typed", () => {
    const conversation = withReply("Fine.");
    const [first, second] = conversation.turns;
    if (!first || !second) throw new Error("the fixture has fewer than two turns");
    const typed = "**Not bold**";
    conversation.inputs[first.invocation_id] = { message_text: typed };
    conversation.inputs[second.invocation_id] = {
      message_text: "**Which repository?**\n\nZenodo",
      reply_answers: { answer_to: first.invocation_id, given_answers: [{ answered_key: "r", answer_values: ["z"] }] },
    };
    const { container } = render(<Transcript conversation={conversation} agents={[]} onToggleRun={() => {}} />);
    const people = container.querySelectorAll(".turn-person");
    expect(within(people[0] as HTMLElement).getByText(typed)).toBeVisible();
    expect(people[1]?.querySelector(".markdown strong")?.textContent).toBe("Which repository?");
  });

  it("offers to try again only on a latest turn that failed", () => {
    render(<Transcript conversation={withReply("Fine.")} agents={[]} onToggleRun={() => {}} onRetry={() => {}} />);
    expect(screen.queryByRole("button", { name: "Try again" })).toBeNull();
  });

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
    const replaced = savedInventory({ digest: "b".repeat(64), inventory_made_at: "x", added_at: "x" });
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

describe("Transcript, a delegated run's project", () => {
  const { agents } = normalise(several as unknown as RawAgentsResponse);
  const runs = { get: () => Promise.resolve(runFixture as unknown as RunResult) } as unknown as RunApi;

  async function openRun(conversation: Conversation, project?: ProjectSummary | null) {
    const child = conversation.turns.flatMap((t) => t.children)[0];
    if (!child) throw new Error("no delegated run in the fixture");
    render(
      <RunApiContext.Provider value={runs}>
        <Transcript
          conversation={conversation}
          agents={agents}
          onToggleRun={() => {}}
          selectedRun={child.invocation_id}
          project={project}
        />
      </RunApiContext.Provider>,
    );
    const review = (await screen.findByText("Human review", { selector: ".not-built strong" })).closest(".not-built");
    if (!(review instanceof HTMLElement)) throw new Error("no human review callout");
    return review;
  }

  it("names and links the conversation's project", async () => {
    const conversation = structuredClone(conversationFixture) as unknown as Conversation;
    const project = {
      ...((projectsFixture as ProjectSummary[])[0] as ProjectSummary),
      project_id: conversation.project_id ?? "",
    };
    const review = await openRun(conversation, project);
    expect(within(review).getByRole("link", { name: projectName(project) })).toHaveAttribute(
      "href",
      `/projects/${encodeURIComponent(project.project_id)}`,
    );
  });

  it("says the run is not part of a project when the conversation has none", async () => {
    const conversation = {
      ...(structuredClone(conversationFixture) as unknown as Conversation),
      project_id: null,
    };
    const review = await openRun(conversation);
    expect(review).toHaveTextContent(/not part of a project/);
    expect(review.querySelector('a[href^="/projects/"]')).toBeNull();
  });

  it("names no project that is not the conversation's", async () => {
    const conversation = structuredClone(conversationFixture) as unknown as Conversation;
    const other = { ...((projectsFixture as ProjectSummary[])[0] as ProjectSummary), project_id: "other" };
    const review = await openRun(conversation, other);
    expect(within(review).queryByRole("link", { name: projectName(other) })).toBeNull();
    expect(review).not.toHaveTextContent(/part of/);
  });
});

describe("Transcript, as a conversation", () => {
  const { agents: directory } = normalise(several as unknown as RawAgentsResponse);
  const greeter = directory.find((a) => a.id === "example.hello");
  if (!greeter) throw new Error("the fixture has no example.hello");
  // The conversation's orchestrator, named as its card would name it.
  const agents = [...directory, { ...greeter, id: "orchestrator.stub", title: "Data Director", icon: "🎬" }];
  const conversation = structuredClone(conversationFixture) as unknown as Conversation;
  const [first] = conversation.turns;
  if (!first) throw new Error("the fixture has no turns");
  const exact = `${first.agent_id}@${first.agent_version}`;

  function turns() {
    const list = screen.getByRole("list", { name: "Conversation" });
    return within(list).getAllByRole("listitem").filter((li) => li.parentElement === list);
  }

  it("is still an ordered list, one item a turn, each the person's part and then the agent's", async () => {
    const { container } = render(<Transcript conversation={conversation} agents={agents} onToggleRun={() => {}} />);
    expect(screen.getByRole("list", { name: "Conversation" }).tagName).toBe("OL");
    expect(turns()).toHaveLength(conversation.turns.length);
    for (const turn of turns()) {
      const parts = [...turn.children].map((c) => c.className);
      expect(parts).toEqual(["turn-person", "turn-agent"]);
    }
    expect((await axe(container)).violations).toEqual([]);
  });

  it("names another member's turn and calls the reader's own turn theirs (#391)", async () => {
    const [first, second] = conversation.turns;
    const colleague = { ...first?.envelope.acting_for, principal_id: COLLEAGUE, name: "Ada Example" };
    const shared = {
      ...conversation,
      turns: [{ ...first, envelope: { ...first?.envelope, acting_for: colleague } }, second],
    } as Conversation;
    render(
      <SessionApiContext.Provider value={fakeSessionApi(DEVELOPMENT)}>
        <Transcript conversation={shared} agents={agents} onToggleRun={() => {}} />
      </SessionApiContext.Provider>,
    );
    const names = () =>
      turns().map((t) => t.querySelector(".turn-person .turn-speaker-name")?.textContent);
    await waitFor(() => expect(names()).toEqual(["👤Ada Example", "👤You"]));
  });

  it("heads a reply with the agent's name alone, not its version or model", () => {
    render(<Transcript conversation={conversation} agents={agents} onToggleRun={() => {}} />);
    const agentPart = turns()[0]?.querySelector(".turn-agent") as HTMLElement;
    const speaker = agentPart.querySelector(".turn-speaker") as HTMLElement;
    expect(speaker.querySelector(".turn-speaker-name")).toHaveTextContent("Data Director");
    expect(within(agentPart).queryByText(exact)).toBeNull();
    expect(within(agentPart).queryByText(/Language model/)).toBeNull();
    const personPart = turns()[0]?.querySelector(".turn-person") as HTMLElement;
    expect(personPart.querySelector(".turn-speaker-name")).toHaveTextContent("You");
  });

  it("marks the person's part with an icon hidden from assistive technology", () => {
    render(<Transcript conversation={conversation} agents={agents} onToggleRun={() => {}} />);
    const personPart = turns()[0]?.querySelector(".turn-person") as HTMLElement;
    const icon = personPart.querySelector(".turn-speaker-name .person-icon");
    expect(icon).not.toBeNull();
    expect(icon).toHaveAttribute("aria-hidden", "true");
  });

  it("names an agent the directory does not list by its id, once", () => {
    render(<Transcript conversation={conversation} agents={[]} onToggleRun={() => {}} />);
    const agentPart = turns()[0]?.querySelector(".turn-agent") as HTMLElement;
    expect(within(agentPart).getAllByText(first.agent_id)).toHaveLength(1);
    expect(within(agentPart).queryByText(exact)).toBeNull();
  });

  it("heads a delegated run with the agent's name", () => {
    render(<Transcript conversation={conversation} agents={agents} onToggleRun={() => {}} />);
    const runs = screen.getAllByRole("list", { name: /delegated to/ })[0] as HTMLElement;
    const card = within(runs).getAllByRole("listitem")[0] as HTMLElement;
    expect(card.querySelector(".turn-speaker-name")).toHaveTextContent(greeter.title);
  });

  it("names the agent working on a reply, laid out as a turn", () => {
    render(
      <Transcript
        conversation={conversation}
        agents={agents}
        onToggleRun={() => {}}
        pending={{ agentId: "orchestrator.stub", message: "hello again" }}
      />,
    );
    const waiting = turns().at(-1) as HTMLElement;
    expect([...waiting.children].map((c) => c.className)).toEqual(["turn-person", "turn-agent"]);
    expect(within(waiting.querySelector(".turn-person") as HTMLElement).getByText("hello again")).toBeVisible();
    expect(waiting.querySelector(".turn-agent")).toHaveTextContent(/Data Director is working on a reply/);
    const icon = waiting.querySelector(".turn-agent .agent-icon");
    expect(icon).toHaveTextContent("🎬");
    expect(icon).toHaveAttribute("aria-hidden", "true");
  });

  it("shows answers being sent as Markdown while the reply is awaited, and a typed message as typed", () => {
    const message = "**Which discipline?**\n\nEnvironmental science\n\n**Which formats?**\n\n_Skipped_";
    const { rerender } = render(
      <Transcript
        conversation={conversation}
        agents={agents}
        onToggleRun={() => {}}
        pending={{ agentId: "orchestrator.stub", message, answers: true }}
      />,
    );
    const person = () => (turns().at(-1) as HTMLElement).querySelector(".turn-person") as HTMLElement;
    expect([...person().querySelectorAll(".markdown strong")].map((s) => s.textContent)).toEqual([
      "Which discipline?",
      "Which formats?",
    ]);
    expect(person().querySelector("em")).toHaveTextContent("Skipped");
    expect(person()).not.toHaveTextContent("**");

    rerender(
      <Transcript
        conversation={conversation}
        agents={agents}
        onToggleRun={() => {}}
        pending={{ agentId: "orchestrator.stub", message: "**as typed**" }}
      />,
    );
    expect(person().querySelector(".markdown")).toBeNull();
    expect(within(person()).getByText("**as typed**")).toBeVisible();
  });

  it("puts the agent's icon before its name, hidden from assistive technology", () => {
    render(<Transcript conversation={conversation} agents={agents} onToggleRun={() => {}} />);
    const name = turns()[0]?.querySelector(".turn-agent .turn-speaker-name") as HTMLElement;
    const icon = name.firstElementChild;
    expect(icon).toHaveClass("agent-icon");
    expect(icon).toHaveTextContent("🎬");
    expect(icon).toHaveAttribute("aria-hidden", "true");
    const personPart = turns()[0]?.querySelector(".turn-person") as HTMLElement;
    expect(personPart.querySelector(".agent-icon")).toBeNull();
  });

  it("gives an agent the directory does not list the default icon", () => {
    render(<Transcript conversation={conversation} agents={[]} onToggleRun={() => {}} />);
    const name = turns()[0]?.querySelector(".turn-agent .turn-speaker-name") as HTMLElement;
    expect(name.querySelector(".agent-icon")).toHaveTextContent(DEFAULT_AGENT_ICON);
  });
});
