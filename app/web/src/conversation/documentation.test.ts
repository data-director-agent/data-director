import type { AgentView } from "../manifest/normalise";
import { type AttachedDocument, checkDocument, documentReaders } from "./documentation";

const CHECKED = { findings: [], kinds: [], checked_with: "presidio-analyzer" };

function sent(fetchMock: ReturnType<typeof vi.fn>): Record<string, unknown> {
  const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
  return JSON.parse(init.body as string) as Record<string, unknown>;
}

describe("checkDocument", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("checks the text read from a PDF as the plain text the project keeps", async () => {
    const fetchMock = vi.fn(() => Promise.resolve(Response.json(CHECKED)));
    vi.stubGlobal("fetch", fetchMock);
    const pdf: AttachedDocument = {
      name: "plan.pdf",
      media_type: "application/pdf",
      text: "Survey responses will be shared in ORDA.",
      size: 40,
      data: "JVBERi0=",
    };

    await checkDocument(pdf);

    expect(sent(fetchMock)).toEqual({ name: pdf.name, media_type: "text/plain", text: pdf.text });
  });

  it("checks a text file under its own media type", async () => {
    const fetchMock = vi.fn(() => Promise.resolve(Response.json(CHECKED)));
    vi.stubGlobal("fetch", fetchMock);
    const notes: AttachedDocument = { name: "notes.md", media_type: "text/markdown", text: "Hi", size: 2 };

    await checkDocument(notes);

    expect(sent(fetchMock)).toMatchObject({ media_type: "text/markdown" });
  });
});

type Agent = Pick<AgentView, "id" | "title" | "readsAttached" | "gate">;
const permitted = { kind: "permitted", actionClass: "advise" } as const;

describe("documentReaders (#1326)", () => {
  it("names the agents whose cards say they read attached text, and the others", () => {
    const agents: Agent[] = [
      { id: "advisor.documentation", title: "Documentation Editor", readsAttached: "to suggest answers", gate: permitted },
      { id: "advisor.policy", title: "Policy Adviser", readsAttached: "", gate: permitted },
      { id: "advisor.untitled", title: "", readsAttached: "", gate: permitted },
    ];
    expect(documentReaders(agents, null)).toEqual({
      readers: [{ name: "the Documentation Editor", readsAttached: "to suggest answers" }],
      others: ["the Policy Adviser", "advisor.untitled"],
    });
  });

  it("leaves out the orchestrator and agents the profile does not permit", () => {
    const agents: Agent[] = [
      { id: "orchestrator", title: "Director", readsAttached: "", gate: permitted },
      { id: "advisor.dmp", title: "Plan Checker", readsAttached: "to read a plan", gate: { kind: "not-permitted" } },
      { id: "advisor.policy", title: "Policy Adviser", readsAttached: "", gate: permitted },
    ];
    expect(documentReaders(agents, "orchestrator")).toEqual({ readers: [], others: ["the Policy Adviser"] });
  });
});
