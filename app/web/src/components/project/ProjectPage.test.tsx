import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";

import disclosureFixture from "../../../fixtures/project-disclosure.json";
import answersFixture from "../../../fixtures/project-answers.json";
import fixture from "../../../fixtures/project-documents.json";
import {
  DecisionConflict,
  type Disclosure,
  type ProjectApi,
  type ProjectDocuments,
  ProjectApiContext,
  digestOf,
} from "../../project/api";
import { ProjectPage } from "./ProjectPage";

// What the server says (app/tests/test_document_decisions.py): a README proposed, and a data
// dictionary already approved.
const PROJECT = fixture as ProjectDocuments;
// The disclosure the server gives (app/tests/test_document_decisions.py): a README a model drafted
// and a person approved as it stood, and a metadata record awaiting a decision.
const DISCLOSURE = disclosureFixture as Disclosure;

function at<T>(items: T[], index: number): T {
  const item = items[index];
  if (item === undefined) throw new Error(`the fixture has no item ${index}`);
  return item;
}

const README = at(PROJECT.documents, 0);
const DICTIONARY = at(PROJECT.documents, 1);
const DRAFT = at(README.versions, 0);

/** `PROJECT` after the README's version 1 is given `state`, as the server would answer. */
function decided(state: "approved" | "rejected", reason: string | null = null): ProjectDocuments {
  const decision = { reason, decided_by: DRAFT.added_by, decided_at: DRAFT.added_at };
  return {
    ...PROJECT,
    documents: [{ ...README, versions: [{ ...DRAFT, state, decision }] }, DICTIONARY],
    decided: { document_id: README.document_id, version: 1 },
  };
}

function fakeApi(overrides: Partial<ProjectApi> = {}): ProjectApi {
  return {
    projects: () => Promise.resolve([]),
    documents: () => Promise.resolve(PROJECT),
    disclosure: () => Promise.resolve(DISCLOSURE),
    decide: () => Promise.resolve(decided("approved")),
    answer: () => Promise.resolve(PROJECT),
    inventory: () => Promise.resolve(null),
    ...overrides,
  };
}

function renderPage(api: ProjectApi, query = "") {
  return render(
    <ProjectApiContext.Provider value={api}>
      <ProjectPage projectId={PROJECT.project_id} query={query} />
    </ProjectApiContext.Provider>,
  );
}

/** `PROJECT` with the README's text and media type replaced, as the given kind of document. */
function withText(text: string, media_type: string): ProjectDocuments {
  const version = { ...DRAFT, text, media_type, digest: digestOf(text) };
  return { ...PROJECT, documents: [{ ...README, versions: [version] }, DICTIONARY] };
}

/** The README rejected at version 1 and redrafted as version 2, still to be decided. */
function redrafted(): ProjectDocuments {
  const text = "# Soil cores\n\nDrafted by a stub.\n";
  const rejected = {
    ...DRAFT,
    state: "rejected" as const,
    decision: { reason: "No site named.", decided_by: DRAFT.added_by, decided_at: DRAFT.added_at },
  };
  const second = { ...DRAFT, version: 2, text, digest: digestOf(text) };
  return { ...PROJECT, documents: [{ ...README, versions: [rejected, second] }, DICTIONARY] };
}

async function readme() {
  return screen.findByRole("article", { name: "README" });
}

/** The page's live region, which says what a decision did; a reader has its own for copying. */
async function pageStatus() {
  const regions = await screen.findAllByRole("status");
  const region = regions.find((element) => !element.closest("article"));
  if (!region) throw new Error("the page has no live region of its own");
  return region;
}

describe("digestOf", () => {
  it("is the SHA-256 the harness records for the text", () => {
    expect(digestOf(DRAFT.text)).toBe(DRAFT.digest);
  });

  it("needs no Web Crypto, which exists only in a secure context", () => {
    vi.stubGlobal("crypto", {});
    try {
      expect(digestOf(DRAFT.text)).toBe(DRAFT.digest);
    } finally {
      vi.unstubAllGlobals();
    }
  });
});

describe("ProjectPage", () => {
  it("lists the documents by state and opens the first waiting for a decision", async () => {
    const { container } = renderPage(fakeApi());
    const article = await readme();
    const list = screen.getByRole("navigation", { name: "Documents" });
    expect(within(list).getByRole("heading", { name: "To review (1)" })).toBeVisible();
    expect(within(list).getByRole("heading", { name: "Approved (1)" })).toBeVisible();
    expect(within(list).getByRole("link", { name: /README/ })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(within(list).getByRole("link", { name: /Data dictionary/ })).toHaveAttribute(
      "href",
      `/projects/${PROJECT.project_id}?doc=${DICTIONARY.document_id}`,
    );

    expect(await within(article).findByRole("heading", { name: "Untitled dataset" })).toBeVisible();
    expect(within(article).getByText("Proposed, not reviewed")).toBeVisible();
    expect(within(article).getByRole("group", { name: "Your decision on version 1" })).toBeVisible();
    expect(screen.queryByRole("article", { name: "Data dictionary" })).not.toBeInTheDocument();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("opens the document the address names, and decides only on what is undecided", async () => {
    renderPage(fakeApi(), `doc=${DICTIONARY.document_id}`);
    const dictionary = await screen.findByRole("article", { name: "Data dictionary" });
    expect(within(dictionary).getByText("Approved")).toBeVisible();
    expect(within(dictionary).queryByRole("group")).not.toBeInTheDocument();
  });

  it("lists the questions a version asks, saying in words which are answered", async () => {
    // app/tests/test_document_answers.py: a README whose one question has been answered.
    const answered = answersFixture as ProjectDocuments;
    const document = at(answered.documents, 0);
    const asked = at(at(document.versions, 0).questions, 0);
    const unanswered = { ...answered, documents: [{ ...document, answers: [] }] };
    const { unmount } = renderPage(fakeApi({ documents: () => Promise.resolve(unanswered) }));
    let questions = await screen.findByRole("region", { name: "Questions for the researcher" });
    expect(questions).toHaveTextContent(asked.question_prompt);
    expect(questions).toHaveTextContent(/Not answered yet/);
    unmount();

    renderPage(fakeApi({ documents: () => Promise.resolve(answered) }));
    questions = await screen.findByRole("region", { name: "Questions for the researcher" });
    expect(questions).toHaveTextContent(/1 of 1 answered/);
    expect(questions).toHaveTextContent(/Answered: .*Soil cores/);
  });

  it("says so when the address names a document the project does not hold", async () => {
    renderPage(fakeApi(), "doc=nonesuch");
    expect(await screen.findByText(/That document is not in this project/)).toBeVisible();
    expect(screen.getByRole("navigation", { name: "Documents" })).toBeVisible();
  });

  it("names the page after the project", async () => {
    const summary = {
      project_id: PROJECT.project_id,
      title: "River loggers",
      created_at: DRAFT.added_at,
      created_by: DRAFT.added_by,
      inventory: null,
      repository: null,
      documents: { proposed: 1, approved: 1, rejected: 0 },
      conversations: [],
    };
    renderPage(fakeApi({ projects: () => Promise.resolve([summary]) }));
    expect(await screen.findByRole("heading", { level: 1, name: "River loggers" })).toBeVisible();
  });

  it("shows the stored text exactly in the Source tab", async () => {
    const user = userEvent.setup();
    renderPage(fakeApi());
    const article = await readme();
    await user.click(within(article).getByRole("tab", { name: "Source" }));
    const panel = within(article).getByRole("tabpanel");
    expect(panel.querySelector("pre")?.textContent).toBe(DRAFT.text);
  });

  it("previews a data dictionary as a table", async () => {
    renderPage(fakeApi(), `doc=${DICTIONARY.document_id}`);
    const dictionary = await screen.findByRole("article", { name: "Data dictionary" });
    const table = await within(dictionary).findByRole("table", { name: "Data dictionary" });
    expect(within(table).getByRole("columnheader", { name: "description" })).toBeVisible();
    expect(within(table).getByRole("cell", { name: "Drafted by a stub." })).toBeVisible();
  });

  it("previews JSON indented, and shows it as stored if it cannot be read", async () => {
    const json = withText('{"title":"Soil"}', "application/json");
    const { unmount } = renderPage(fakeApi({ documents: () => Promise.resolve(json) }));
    let article = await readme();
    expect(await within(article).findByText(/"title": "Soil"/)).toBeVisible();
    unmount();

    const broken = withText("{not json", "application/json");
    renderPage(fakeApi({ documents: () => Promise.resolve(broken) }));
    article = await readme();
    expect(await within(article).findByText(/could not be read as JSON/)).toBeVisible();
    expect(within(article).getByText("{not json")).toBeVisible();
  });

  it("previews the person's edit before they approve it", async () => {
    const user = userEvent.setup();
    renderPage(fakeApi());
    const article = await readme();
    await user.click(within(article).getByLabelText("Edit it, then approve my version"));
    const edited = within(article).getByLabelText("Your version of the text");
    await user.clear(edited);
    await user.type(edited, "# Soil cores");
    expect(within(article).getByText(/The preview shows your edited version/)).toBeVisible();
    expect(within(article).getByRole("heading", { name: "Soil cores" })).toBeVisible();

    await user.click(within(article).getByLabelText("Approve version 1 as it is"));
    expect(within(article).getByRole("heading", { name: "Untitled dataset" })).toBeVisible();
  });

  it("lists every version, with what each changed", async () => {
    const user = userEvent.setup();
    renderPage(fakeApi({ documents: () => Promise.resolve(redrafted()) }));
    const article = await readme();
    await user.click(within(article).getByRole("tab", { name: "Versions (2)" }));
    const panel = within(article).getByRole("tabpanel");
    expect(within(panel).getByText("Version 2 (shown)")).toBeVisible();
    expect(within(panel).getByRole("link", { name: "Version 1" })).toHaveAttribute(
      "href",
      `/projects/${PROJECT.project_id}?doc=${README.document_id}&v=1`,
    );
    expect(within(panel).getByText("No site named.")).toBeVisible();

    await user.click(within(panel).getByText("Changes from version 1"));
    expect(panel.querySelector("del")).toHaveTextContent("Untitled dataset");
    expect(panel.querySelector("ins")).toHaveTextContent("Soil cores");
    expect(within(panel).getByText("1 line added, 1 line removed.")).toBeVisible();
  });

  it("shows an earlier version read-only, with a way back to the latest", async () => {
    renderPage(
      fakeApi({ documents: () => Promise.resolve(redrafted()) }),
      `doc=${README.document_id}&v=1`,
    );
    const article = await readme();
    expect(within(article).getByText(/This is version 1, kept as it was/)).toBeVisible();
    expect(within(article).getByRole("link", { name: "Read the latest version" })).toHaveAttribute(
      "href",
      `/projects/${PROJECT.project_id}?doc=${README.document_id}`,
    );
    expect(within(article).getByText("Rejected")).toBeVisible();
    expect(within(article).queryByRole("group")).not.toBeInTheDocument();
  });

  it("shows how generative AI was used as the list's last entry", async () => {
    const { container } = renderPage(fakeApi(), "doc=disclosure");
    expect(await screen.findByRole("heading", { name: "Use of generative AI" })).toBeVisible();
    expect(screen.queryByRole("article")).not.toBeInTheDocument();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("offers the next document to review once one is decided", async () => {
    const waiting = {
      ...DICTIONARY,
      versions: [{ ...at(DICTIONARY.versions, 0), state: "proposed" as const, decision: null }],
    };
    const both = { ...PROJECT, documents: [README, waiting] };
    const approved = decided("approved");
    const after = { ...approved, documents: [at(approved.documents, 0), waiting] };
    const user = userEvent.setup();
    renderPage(
      fakeApi({ documents: () => Promise.resolve(both), decide: () => Promise.resolve(after) }),
    );
    const article = await readme();
    await user.click(within(article).getByRole("button", { name: "Approve version 1" }));
    const said = await screen.findByText(/README: version 1 approved/);
    expect(said).toHaveTextContent(/Data dictionary/);
    expect(within(said).getByRole("link", { name: "Data dictionary" })).toHaveAttribute(
      "href",
      `/projects/${PROJECT.project_id}?doc=${DICTIONARY.document_id}`,
    );
  });

  it("approves as drafted without asking for a reason, naming the text shown", async () => {
    const decide = vi.fn<ProjectApi["decide"]>(() => Promise.resolve(decided("approved")));
    const user = userEvent.setup();
    renderPage(fakeApi({ decide }));
    const article = await readme();
    expect(within(article).getByLabelText("Reason (optional)")).not.toBeRequired();
    await user.click(within(article).getByRole("button", { name: "Approve version 1" }));

    expect(decide).toHaveBeenCalledWith(PROJECT.project_id, README.document_id, {
      version: 1,
      digest: DRAFT.digest,
      decision: "approved",
    });
    expect(await pageStatus()).toHaveTextContent("README: version 1 approved.");
    expect(within(article).getByText("Approved")).toBeVisible();
    expect(within(article).queryByRole("group")).not.toBeInTheDocument();
    // The form has gone, so the focus goes to the document it was about.
    expect(within(article).getByRole("heading", { name: "README" })).toHaveFocus();
  });

  it("asks for a reason to reject, and sends it", async () => {
    const decide = vi.fn<ProjectApi["decide"]>(() =>
      Promise.resolve(decided("rejected", "No site named.")),
    );
    const user = userEvent.setup();
    renderPage(fakeApi({ decide }));
    const article = await readme();
    await user.click(within(article).getByLabelText("Reject version 1"));
    const reason = within(article).getByLabelText("Reason (required)");
    expect(reason).toBeRequired();
    await user.click(within(article).getByRole("button", { name: "Reject version 1" }));
    expect(decide).not.toHaveBeenCalled(); // the browser stops a required field left empty

    await user.type(reason, "No site named.");
    await user.click(within(article).getByRole("button", { name: "Reject version 1" }));
    expect(decide.mock.lastCall?.[2]).toMatchObject({ decision: "rejected", reason: "No site named." });
    expect(await pageStatus()).toHaveTextContent("README: version 1 rejected.");
    expect(within(article).getByText("No site named.")).toBeVisible();
  });

  it("edits then approves in one request, with the keyboard alone", async () => {
    const decide = vi.fn<ProjectApi["decide"]>(() =>
      Promise.resolve({ ...decided("approved"), decided: { document_id: README.document_id, version: 2 } }),
    );
    const user = userEvent.setup();
    renderPage(fakeApi({ decide }));
    const article = await readme();
    within(article).getByLabelText("Approve version 1 as it is").focus();
    await user.keyboard("{ArrowDown}");
    const edited = within(article).getByLabelText("Your version of the text");
    await user.clear(edited);
    await user.type(edited, "# Soil cores");
    await user.type(within(article).getByLabelText("Reason (required)"), "Named it.");
    await user.click(within(article).getByRole("button", { name: "Approve my edited version" }));
    expect(decide.mock.lastCall?.[2]).toEqual({
      version: 1,
      digest: DRAFT.digest, // the text shown, not the text sent
      decision: "approved",
      reason: "Named it.",
      edited_text: "# Soil cores",
    });
    expect(await pageStatus()).toHaveTextContent(
      "README: your edited version 2 approved.",
    );
  });

  it("reads the project again when the document has moved on, and says so", async () => {
    const documents = vi.fn(() => Promise.resolve(PROJECT));
    const conflict = new DecisionConflict({
      type: "https://w3id.org/data-director/problems/version-not-latest",
      title: "The document has moved on",
      detail: "Version 1 is not the latest: version 2 is.",
    });
    const user = userEvent.setup();
    renderPage(fakeApi({ documents, decide: () => Promise.reject(conflict) }));
    const article = await readme();
    await user.click(within(article).getByRole("button", { name: "Approve version 1" }));
    const alert = await within(article).findByRole("alert");
    expect(alert).toHaveTextContent("Version 1 is not the latest: version 2 is.");
    expect(alert).toHaveFocus();
    expect(documents).toHaveBeenCalledTimes(2);
  });

  it("keeps the documents and says why when the project cannot be read again", async () => {
    let reads = 0;
    const documents = vi.fn(() =>
      reads++ === 0 ? Promise.resolve(PROJECT) : Promise.reject(new Error("The network is down.")),
    );
    const conflict = new DecisionConflict({
      type: "https://w3id.org/data-director/problems/version-not-latest",
      title: "The document has moved on",
      detail: "Version 1 is not the latest: version 2 is.",
    });
    const user = userEvent.setup();
    renderPage(fakeApi({ documents, decide: () => Promise.reject(conflict) }));
    const article = await readme();
    await user.click(within(article).getByRole("button", { name: "Approve version 1" }));
    const alert = await within(article).findByRole("alert");
    expect(alert).toHaveTextContent("Version 1 is not the latest: version 2 is.");
    expect(alert).toHaveTextContent(/The network is down/);
    expect(alert).toHaveFocus();
    expect(within(article).getByRole("heading", { name: "Untitled dataset" })).toBeVisible();
    expect(screen.getByRole("link", { name: /Data dictionary/ })).toBeVisible();
  });

  it("gives an edit of a CRLF document its CRLF line endings back", async () => {
    const text = "# Soil\r\n\r\nCores.\r\n";
    const crlf = {
      ...PROJECT,
      documents: [{ ...README, versions: [{ ...DRAFT, text, digest: digestOf(text) }] }, DICTIONARY],
    };
    const decide = vi.fn<ProjectApi["decide"]>(() => Promise.resolve(decided("approved")));
    const user = userEvent.setup();
    renderPage(fakeApi({ documents: () => Promise.resolve(crlf), decide }));
    const article = await readme();
    await user.click(within(article).getByLabelText("Edit it, then approve my version"));
    const edited = within(article).getByLabelText("Your version of the text");
    await user.clear(edited);
    await user.type(edited, "# Soil cores{Enter}{Enter}Cores.{Enter}");
    await user.type(within(article).getByLabelText("Reason (required)"), "Named it.");
    await user.click(within(article).getByRole("button", { name: "Approve my edited version" }));
    expect(decide.mock.lastCall?.[2]).toMatchObject({
      digest: digestOf(text),
      edited_text: "# Soil cores\r\n\r\nCores.\r\n",
    });
  });
});
