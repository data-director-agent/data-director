import { type AttachedDocument, checkDocument } from "./documentation";

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
