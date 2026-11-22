import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";

import answersFixture from "../../../fixtures/project-answers.json";
import {
  DecisionConflict,
  type ProjectApi,
  type ProjectDocuments,
  type ProjectSummary,
  ProjectApiContext,
  digestOf,
} from "../../project/api";
import { type ConversationApi, ConversationApiContext } from "../../conversation/api";
import type { DocumentationSummary } from "../../conversation/documentation";
import { projectSummary } from "../../test/api";
import {
  DICTIONARY,
  DRAFT,
  PROJECT,
  README,
  at,
  decided,
  fakeProjectApi,
} from "../../test/projectApi";
import { ProjectPage } from "./ProjectPage";

const fakeApi = fakeProjectApi;

function fakeConversations(
  list: ConversationApi["list"] = () => Promise.resolve([]),
): ConversationApi {
  return {
    create: () => Promise.reject(new Error("nothing started in these tests")),
    list,
    get: () => Promise.reject(new Error("nothing opened in these tests")),
    remove: () => Promise.reject(new Error("nothing deleted in these tests")),
    restore: () => Promise.resolve(),
    deleted: () => Promise.resolve([]),
  };
}

function renderPage(api: ProjectApi, query = "", conversations = fakeConversations()) {
  return render(
    <ConversationApiContext.Provider value={conversations}>
      <ProjectApiContext.Provider value={api}>
        <ProjectPage projectId={PROJECT.project_id} query={query} />
      </ProjectApiContext.Provider>
    </ConversationApiContext.Provider>,
  );
}

/** A data management plan attached as a Word document. */
const DMP: DocumentationSummary = {
  documentation_name: "dmp.docx",
  documentation_digest: "a".repeat(64),
  documentation_media_type: "text/plain",
  documentation_size: 2048,
  documentation_added_at: "2026-11-10T10:00:00Z",
  documentation_source_media_type:
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
};
const DMP_MARKDOWN = "# Data management plan\n\n## Data collection\n\nSoil cores, weekly.\n";
const DMP_STORED = "Data management plan Data collection Soil cores, weekly.";

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

/** Choose to approve version 1 as it is, which nothing pre-selects, and press the button. */
async function approveAsItIs(user: ReturnType<typeof userEvent.setup>, article: HTMLElement) {
  await user.click(within(article).getByLabelText("Approve version 1 as it is"));
  await user.click(within(article).getByRole("button", { name: "Approve version 1" }));
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
    let questions = await screen.findByRole("region", { name: "Questions" });
    expect(questions).toHaveTextContent(/0 of 1 answered/);
    expect(within(questions).getByRole("textbox", { name: asked.question_prompt })).toBeVisible();
    expect(within(questions).queryByText(/Answered \(/)).not.toBeInTheDocument();
    unmount();

    renderPage(fakeApi({ documents: () => Promise.resolve(answered) }));
    questions = await screen.findByRole("region", { name: "Questions" });
    expect(questions).toHaveTextContent(/1 of 1 answered/);
    // An answered question is folded away beneath the form, not asked again.
    expect(within(questions).getByText("Answered (1)")).toBeVisible();
    expect(questions).toHaveTextContent(/Answered: .*Soil cores/);
    expect(within(questions).queryByRole("textbox")).not.toBeInTheDocument();
  });

  it("asks each question once, with a model's suggestion in its box to check and accept", async () => {
    const answered = answersFixture as ProjectDocuments;
    const document = at(answered.documents, 0);
    const version = at(document.versions, 0);
    const asked = at(version.questions, 0);
    const suggesting = {
      ...answered,
      documents: [
        {
          ...document,
          answers: [],
          versions: [
            {
              ...version,
              questions: [
                { ...asked, suggested_answer: "Cores at 0 to 10 cm", suggestion_derivation: "model" },
              ],
            },
          ],
        },
      ],
    };
    const { container } = renderPage(fakeApi({ documents: () => Promise.resolve(suggesting) }));
    const questions = await screen.findByRole("region", { name: "Questions" });
    expect(questions).toHaveTextContent(/0 of 1 answered/);
    expect(within(questions).getAllByText(asked.question_prompt)).toHaveLength(1);
    expect(within(questions).getByRole("textbox", { name: asked.question_prompt })).toHaveValue(
      "Cores at 0 to 10 cm",
    );
    expect(within(questions).getByRole("button", { name: "Accept 1 suggested answer" })).toBeEnabled();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("answers the latest version's open questions on the page, with the conversation's form", async () => {
    const answered = answersFixture as ProjectDocuments;
    const document = at(answered.documents, 0);
    const version = at(document.versions, 0);
    const asked = at(version.questions, 0);
    const unanswered = { ...answered, documents: [{ ...document, answers: [] }] };
    const sent: unknown[] = [];
    const api = fakeApi({
      documents: () => Promise.resolve(unanswered),
      answer: (...args) => {
        sent.push(args);
        return Promise.resolve(answered);
      },
    });
    const { container } = renderPage(api);
    const box = await screen.findByRole("textbox", { name: asked.question_prompt });
    expect(await axe(container)).toHaveNoViolations();
    await userEvent.type(box, "Soil cores");
    await userEvent.click(screen.getByRole("button", { name: "Save answers" }));
    expect(sent).toEqual([
      [
        PROJECT.project_id,
        document.document_id,
        version.version,
        [{ answered_question: asked.question_id, answer_text: "Soil cores" }],
      ],
    ]);
    const questions = await screen.findByRole("region", { name: "Questions" });
    expect(questions).toHaveTextContent(/1 of 1 answered/);
    expect(screen.queryByRole("textbox", { name: asked.question_prompt })).not.toBeInTheDocument();
    expect(await screen.findByText(/Recorded 1 answer/)).toBeVisible();
  });

  it("offers no answer boxes for an earlier version's questions", async () => {
    const answered = answersFixture as ProjectDocuments;
    const document = at(answered.documents, 0);
    const first = at(document.versions, 0);
    const second = { ...first, version: 2, questions: [], revises: { document_id: first.document_id, version: 1 } };
    const twice = { ...answered, documents: [{ ...document, answers: [], versions: [first, second] }] };
    renderPage(fakeApi({ documents: () => Promise.resolve(twice) }), `doc=${document.document_id}&v=1`);
    const questions = await screen.findByRole("region", { name: "Questions" });
    expect(questions).toHaveTextContent(/asked of an earlier version/);
    expect(screen.queryByRole("textbox", { name: at(first.questions, 0).question_prompt })).not.toBeInTheDocument();
  });

  it("says so when the address names a document the project does not hold", async () => {
    renderPage(fakeApi(), "doc=nonesuch");
    expect(await screen.findByText(/That document is not in this project/)).toBeVisible();
    expect(screen.getByRole("navigation", { name: "Documents" })).toBeVisible();
  });

  it("lists no conversations beside its documents", async () => {
    renderPage(fakeApi());
    await readme();
    expect(screen.queryByRole("navigation", { name: /Conversations/ })).toBeNull();
  });

  it("lists the attached documents and opens one laid out, with its original to download", async () => {
    const documentationText = vi.fn<ProjectApi["documentationText"]>((_p, _d, preview) =>
      Promise.resolve(
        preview
          ? { text: DMP_MARKDOWN, mediaType: "text/markdown" }
          : { text: DMP_STORED, mediaType: "text/plain" },
      ),
    );
    const { container } = renderPage(
      fakeApi({ documentation: () => Promise.resolve([DMP]), documentationText }),
      `attached=${DMP.documentation_digest}`,
    );
    const article = await screen.findByRole("article", { name: DMP.documentation_name });
    const list = screen.getByRole("navigation", { name: "Documents" });
    const entry = within(list).getByRole("link", { name: new RegExp(DMP.documentation_name) });
    expect(entry.getAttribute("aria-current")).toBe("page");
    expect(entry.getAttribute("href")).toContain(`attached=${DMP.documentation_digest}`);
    expect(await within(article).findByRole("heading", { name: "Data collection" })).toBeVisible();
    const download = within(article).getByRole("link", { name: /Download/ });
    expect(download.getAttribute("href")).toMatch(/\/documentation\/.+\?original$/);
    await userEvent.click(within(article).getByRole("tab", { name: "Text" }));
    expect(within(article).getByText(DMP_STORED)).toBeVisible();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("opens the first attached document when nothing has been drafted", async () => {
    renderPage(
      fakeApi({
        documents: () => Promise.resolve({ ...PROJECT, documents: [] }),
        documentation: () => Promise.resolve([DMP]),
        documentationText: () => Promise.resolve({ text: DMP_MARKDOWN, mediaType: "text/markdown" }),
      }),
    );
    expect(await screen.findByRole("article", { name: DMP.documentation_name })).toBeVisible();
  });

  it("says so when the address names an attached document the project does not hold", async () => {
    renderPage(fakeApi(), "attached=nonesuch");
    expect(await screen.findByText(/That document is not in this project/)).toBeVisible();
  });

  it("says so when an attached document's text cannot be read", async () => {
    renderPage(
      fakeApi({
        documentation: () => Promise.resolve([DMP]),
        documentationText: () => Promise.reject(new Error("unreachable")),
      }),
      `attached=${DMP.documentation_digest}`,
    );
    const article = await screen.findByRole("article", { name: DMP.documentation_name });
    expect(await within(article).findByRole("alert")).toBeVisible();
    expect(within(article).queryByRole("tab")).toBeNull();
  });

  it("names the page after the project", async () => {
    const summary = projectSummary({
      project_id: PROJECT.project_id,
      title: "River loggers",
      created_at: DRAFT.added_at,
      created_by: DRAFT.added_by,
      inventory: null,
      repository: null,
      documents: { proposed: 1, approved: 1, rejected: 0 },
      conversations: [],
    });
    renderPage(fakeApi({ projects: () => Promise.resolve([summary]) }));
    expect(await screen.findByRole("heading", { level: 1, name: "River loggers" })).toBeVisible();
  });

  it("renames the project and shows the name the server reads back", async () => {
    const user = userEvent.setup();
    const summary: ProjectSummary = projectSummary({
      project_id: PROJECT.project_id,
      title: "Sediment cores",
      title_source: "model",
      created_at: DRAFT.added_at,
      created_by: DRAFT.added_by,
      inventory: null,
      repository: null,
      documents: { proposed: 1, approved: 1, rejected: 0 },
      conversations: [],
    });
    let current = summary;
    const rename = vi.fn((_: string, title: string) => {
      current = { ...summary, title, title_source: "researcher" };
      return Promise.resolve(current);
    });
    renderPage(fakeApi({ projects: () => Promise.resolve([current]), rename }));
    expect(await screen.findByRole("heading", { level: 1, name: "Sediment cores" })).toBeVisible();

    await user.click(screen.getByRole("button", { name: "Rename project" }));
    const dialog = await screen.findByRole("dialog", { name: "Rename project" });
    expect(within(dialog).getByText(/suggested this name/)).toBeVisible();
    const field = within(dialog).getByRole("textbox", { name: "Project name" });
    expect(field).toHaveValue("Sediment cores");
    await user.clear(field);
    await user.type(field, "  Humber estuary cores ");
    await user.click(within(dialog).getByRole("button", { name: "Save name" }));

    expect(rename).toHaveBeenCalledWith(PROJECT.project_id, "Humber estuary cores");
    expect(
      await screen.findByRole("heading", { level: 1, name: "Humber estuary cores" }),
    ).toBeVisible();
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("says why a rename was refused and keeps the dialog open", async () => {
    const user = userEvent.setup();
    const summary = projectSummary({
      project_id: PROJECT.project_id,
      title: null,
      created_at: DRAFT.added_at,
      created_by: DRAFT.added_by,
      inventory: null,
      repository: null,
      documents: { proposed: 1, approved: 1, rejected: 0 },
      conversations: [],
    });
    renderPage(
      fakeApi({
        projects: () => Promise.resolve([summary]),
        rename: () => Promise.reject(new Error("the server answered 400")),
      }),
    );
    await user.click(await screen.findByRole("button", { name: "Rename project" }));
    const dialog = await screen.findByRole("dialog", { name: "Rename project" });
    const field = within(dialog).getByRole("textbox", { name: "Project name" });
    await user.clear(field);
    await user.type(field, "Soil");
    await user.click(within(dialog).getByRole("button", { name: "Save name" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent(
      "could not rename this project: the server answered 400",
    );
  });

  it("deletes the project only once its name is typed, and says what stays", async () => {
    const user = userEvent.setup();
    history.pushState(null, "", `/projects/${PROJECT.project_id}`);
    const summary: ProjectSummary = projectSummary({
      project_id: PROJECT.project_id,
      title: "Sediment cores",
      title_source: "researcher",
      created_at: DRAFT.added_at,
      created_by: DRAFT.added_by,
      inventory: null,
      repository: null,
      documents: { proposed: 1, approved: 1, rejected: 0 },
      conversations: [],
      restore_days: 30,
    });
    const remove = vi.fn<ProjectApi["remove"]>(() =>
      Promise.resolve({
        ...summary,
        deleted: { at: DRAFT.added_at, by: DRAFT.added_by, restorable_until: DRAFT.added_at },
      }),
    );
    renderPage(fakeApi({ projects: () => Promise.resolve([summary]), remove }));

    await user.click(await screen.findByRole("button", { name: "Delete project" }));
    const dialog = await screen.findByRole("dialog", { name: "Delete project" });
    expect(within(dialog).getByText(/Nothing is erased/)).toBeVisible();
    expect(within(dialog).getByText(/not recalled/)).toBeVisible();
    expect(within(dialog).getByText(/restore it from the Projects page until/)).toBeVisible();
    expect(await axe(dialog)).toHaveNoViolations();
    const confirm = within(dialog).getByRole("button", { name: "Delete project" });
    const field = within(dialog).getByRole("textbox", { name: /to confirm/ });
    await user.type(field, "Sediment");
    expect(confirm).toBeDisabled();
    await user.click(confirm);
    expect(remove).not.toHaveBeenCalled();

    await user.type(field, " cores");
    expect(confirm).toBeEnabled();
    await user.click(confirm);
    expect(remove).toHaveBeenCalledWith(PROJECT.project_id, "Sediment cores");
    await vi.waitFor(() => expect(window.location.pathname).toBe("/projects"));
  });

  it("says why a deletion was refused and keeps the dialog open", async () => {
    const user = userEvent.setup();
    const summary: ProjectSummary = projectSummary({
      project_id: PROJECT.project_id,
      title: "Sediment cores",
      created_at: DRAFT.added_at,
      created_by: DRAFT.added_by,
      inventory: null,
      repository: null,
      documents: { proposed: 1, approved: 1, rejected: 0 },
      conversations: [],
      restore_days: 0,
    });
    renderPage(
      fakeApi({
        projects: () => Promise.resolve([summary]),
        remove: () => Promise.reject(new Error("the server answered 403")),
      }),
    );
    await user.click(await screen.findByRole("button", { name: "Delete project" }));
    const dialog = await screen.findByRole("dialog", { name: "Delete project" });
    expect(within(dialog).getByText(/does not let a deleted project be restored/)).toBeVisible();
    await user.type(within(dialog).getByRole("textbox", { name: /to confirm/ }), "Sediment cores");
    await user.click(within(dialog).getByRole("button", { name: "Delete project" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent(
      "could not delete this project: the server answered 403",
    );
  });

  it("shows the stored text exactly in the Source tab", async () => {
    const user = userEvent.setup();
    renderPage(fakeApi());
    const article = await readme();
    await user.click(await within(article).findByRole("tab", { name: "Source" }));
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

  it("offers no decision on a README that only asks questions first", async () => {
    const asking = {
      ...PROJECT,
      documents: [{ ...README, versions: [{ ...DRAFT, stage: "questions" as const }] }, DICTIONARY],
    };
    renderPage(fakeApi({ documents: () => Promise.resolve(asking) }));
    const article = await readme();
    expect(within(article).getByText(/not the README yet/)).toBeVisible();
    expect(within(article).queryByLabelText("Approve version 1 as it is")).toBeNull();
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
    await user.click(await within(article).findByRole("tab", { name: "Versions (2)" }));
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

  it.each([
    ["researchers", "people"],
    ["facts", "facts"],
    ["repository", "repository"],
    ["disclosure", "ai-use"],
    ["deposit", "deposit"],
  ])("sends an old link to the %s panel on to its tab", async (doc, tab) => {
    history.replaceState(null, "", `/projects/${PROJECT.project_id}?doc=${doc}`);
    renderPage(fakeApi(), `doc=${doc}`);
    await vi.waitFor(() =>
      expect(location.pathname).toBe(`/projects/${PROJECT.project_id}/${tab}`),
    );
    expect(location.search).toBe("");
  });

  it("lists only documents beside the reader; the rest are tabs", async () => {
    renderPage(fakeApi());
    await readme();
    const list = screen.getByRole("navigation", { name: "Documents" });
    expect(within(list).queryByRole("link", { name: "Repository" })).toBeNull();
    expect(within(list).queryByText("About the documents")).toBeNull();
  });

  it("reaches the repository even before any document is drafted", async () => {
    const empty = { ...PROJECT, documents: [] };
    renderPage(fakeApi({ documents: () => Promise.resolve(empty) }));
    expect(await screen.findByRole("heading", { name: "No documents yet" })).toBeVisible();
    expect(screen.getByRole("link", { name: "Repository" })).toBeVisible();
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
    await approveAsItIs(user, article);
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
    await approveAsItIs(user, article);

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
    await approveAsItIs(user, article);
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
    await approveAsItIs(user, article);
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

describe("ProjectPage, before a version with gaps is approved (#1282)", () => {
  // Three gaps, one of whose questions has been answered: the answer is not in this version.
  const questions = ["Description", "Methods", "Licence"].map((section, i) => ({
    question_id: `q-${String(i).padStart(16, "0")}`,
    question_prompt: `What goes in ${section}?`,
    gap_section: section,
  }));
  const answered = {
    question_id: at(questions, 0).question_id,
    answer_text: "Soil cores",
    answered_at: DRAFT.added_at,
    answered_by: DRAFT.added_by,
    version: 1,
  };
  const gappy: ProjectDocuments = {
    ...PROJECT,
    documents: [{ ...README, answers: [answered], versions: [{ ...DRAFT, questions }] }, DICTIONARY],
  };

  function decisionGroup(article: HTMLElement) {
    return within(article).getByRole("group", { name: "Your decision on version 1" });
  }

  it("chooses no decision for the person, and records nothing until they choose", async () => {
    const decide = vi.fn<ProjectApi["decide"]>(() => Promise.resolve(decided("approved")));
    const user = userEvent.setup();
    renderPage(fakeApi({ documents: () => Promise.resolve(gappy), decide }));
    const article = await readme();
    for (const radio of within(decisionGroup(article)).getAllByRole("radio")) {
      expect(radio).not.toBeChecked();
      expect(radio).toBeRequired();
    }
    await user.click(within(article).getByRole("button", { name: "Record my decision" }));
    expect(decide).not.toHaveBeenCalled(); // the browser stops a required choice left unmade
  });

  it("counts the gaps and open questions beside the decision, and keeps a way to it in view", async () => {
    const user = userEvent.setup();
    renderPage(fakeApi({ documents: () => Promise.resolve(gappy) }));
    const article = await readme();
    const submit = within(article).getByRole("button", { name: "Record my decision" });
    expect(submit).toHaveAccessibleDescription(/3 gaps and 2 open questions/);

    const go = within(article).getByRole("button", { name: "Decide on version 1" });
    expect(go.parentElement).toHaveTextContent(/3 gaps, 2 open questions/);
    await user.click(go);
    expect(within(decisionGroup(article)).getAllByRole("radio")[0]).toHaveFocus();
    // The draft's own headings are the preview's; what this change adds is checked here.
    expect(await axe(go.parentElement as HTMLElement)).toHaveNoViolations();
    expect(await axe(submit.closest("form") as HTMLElement)).toHaveNoViolations();
  });

  it("asks again before approving it as it is, naming the count, and Escape records nothing", async () => {
    const decide = vi.fn<ProjectApi["decide"]>(() => Promise.resolve(decided("approved")));
    const user = userEvent.setup();
    renderPage(fakeApi({ documents: () => Promise.resolve(gappy), decide }));
    const article = await readme();
    await approveAsItIs(user, article);

    const dialog = await screen.findByRole("dialog", { name: /3 gaps/ });
    expect(dialog).toContainElement(document.activeElement as HTMLElement);
    expect(await axe(dialog)).toHaveNoViolations();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(decide).not.toHaveBeenCalled();

    await user.click(within(article).getByRole("button", { name: "Approve version 1" }));
    const again = await screen.findByRole("dialog", { name: /3 gaps/ });
    await user.click(within(again).getByRole("button", { name: /Approve with 3 gaps/ }));
    expect(decide).toHaveBeenCalledWith(PROJECT.project_id, README.document_id, {
      version: 1,
      digest: DRAFT.digest,
      decision: "approved",
    });
    expect(await pageStatus()).toHaveTextContent("README: version 1 approved.");
  });

  it("does not ask again before approving a version with no gaps", async () => {
    const decide = vi.fn<ProjectApi["decide"]>(() => Promise.resolve(decided("approved")));
    const user = userEvent.setup();
    renderPage(fakeApi({ decide }));
    await approveAsItIs(user, await readme());
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(decide).toHaveBeenCalledTimes(1);
  });

  it("rejects without asking again, still needing its reason", async () => {
    const decide = vi.fn<ProjectApi["decide"]>(() =>
      Promise.resolve(decided("rejected", "Too many gaps.")),
    );
    const user = userEvent.setup();
    renderPage(fakeApi({ documents: () => Promise.resolve(gappy), decide }));
    const article = await readme();
    await user.click(within(article).getByLabelText("Reject version 1"));
    expect(within(article).getByLabelText("Reason (required)")).toBeRequired();
    await user.type(within(article).getByLabelText("Reason (required)"), "Too many gaps.");
    await user.click(within(article).getByRole("button", { name: "Reject version 1" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(decide.mock.lastCall?.[2]).toMatchObject({ decision: "rejected", reason: "Too many gaps." });
  });
});
