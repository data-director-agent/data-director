import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";

import disclosureFixture from "../../../fixtures/project-disclosure.json";
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
    inventory: () => Promise.resolve(null),
    ...overrides,
  };
}

function renderPage(api: ProjectApi) {
  return render(
    <ProjectApiContext.Provider value={api}>
      <ProjectPage projectId={PROJECT.project_id} />
    </ProjectApiContext.Provider>,
  );
}

async function readme() {
  return screen.findByRole("article", { name: "README" });
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
  it("shows each document's state and text, and decides only on what is undecided", async () => {
    const { container } = renderPage(fakeApi());
    const article = await readme();
    expect(within(article).getByText("Proposed, not reviewed")).toBeVisible();
    expect(within(article).getByText(/Drafted by a stub/)).toBeVisible();
    expect(within(article).getByRole("group", { name: "Your decision on version 1" })).toBeVisible();

    const dictionary = screen.getByRole("article", { name: "Data dictionary" });
    expect(within(dictionary).getByText("Approved")).toBeVisible();
    expect(within(dictionary).queryByRole("group")).not.toBeInTheDocument();
    expect(await axe(container)).toHaveNoViolations();
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
    expect(await screen.findByRole("status")).toHaveTextContent("README: version 1 approved.");
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
    expect(await screen.findByRole("status")).toHaveTextContent("README: version 1 rejected.");
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
    expect(await screen.findByRole("status")).toHaveTextContent(
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
    expect(alert).toHaveTextContent("could not read the latest version: The network is down.");
    expect(alert).toHaveFocus();
    expect(screen.getByRole("article", { name: "Data dictionary" })).toBeVisible();
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
