import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";

import fixture from "../../../fixtures/project-drafted.json";
import {
  DecisionConflict,
  type DocumentVersion,
  type ProjectApi,
  ProjectApiContext,
  type ProjectDocument,
  type ProjectDocuments,
  httpProjectApi,
} from "../../project/api";
import { ContinueDrafting } from "./ContinueDrafting";

// What the server says after a request for a new draft (app/tests/test_document_drafts.py): a
// README's version 1, which asks a question since answered, and version 2, drafted from it.
const DRAFTED = fixture as ProjectDocuments;
const README = DRAFTED.documents[0];
if (!README) throw new Error("the fixture has no document");
const [first, second] = README.versions;
if (!first || !second) throw new Error("the fixture has no second draft");
const FIRST: DocumentVersion = first;
const SECOND: DocumentVersion = second;
// The document as the page held it before the run: only its first version.
const BEFORE: ProjectDocument = { ...README, versions: [FIRST] };

function renderForm(
  draft: ProjectApi["draft"],
  { document = BEFORE, version = FIRST, isLatest = true }: {
    document?: ProjectDocument;
    version?: DocumentVersion;
    isLatest?: boolean;
  } = {},
) {
  const onDrafted = vi.fn();
  const onStale = vi.fn(() => Promise.resolve());
  const view = render(
    <ProjectApiContext.Provider value={{ ...httpProjectApi, draft }}>
      <ContinueDrafting
        projectId={DRAFTED.project_id}
        document={document}
        version={version}
        name="README"
        isLatest={isLatest}
        onDrafted={onDrafted}
        onStale={onStale}
      />
    </ProjectApiContext.Provider>,
  );
  return { ...view, onDrafted, onStale };
}

test("a request names the latest version shown, and says which version it drafted", async () => {
  const draft = vi.fn<ProjectApi["draft"]>(() => Promise.resolve(DRAFTED));
  const { container, onDrafted } = renderForm(draft);
  expect(await axe(container)).toHaveNoViolations();

  await userEvent.click(screen.getByRole("button", { name: "Continue drafting" }));

  expect(draft).toHaveBeenCalledWith(DRAFTED.project_id, FIRST.document_id, FIRST.version);
  expect(onDrafted).toHaveBeenCalledWith(DRAFTED);
  expect(await screen.findByRole("status")).toHaveTextContent(`Version ${SECOND.version}`);
});

test("it is offered with every question answered", () => {
  expect(BEFORE.answers.length).toBeGreaterThan(0);
  renderForm(vi.fn<ProjectApi["draft"]>());
  expect(screen.getByRole("button", { name: "Continue drafting" })).toBeEnabled();
});

test("when the agent drafts no version, the status says why in its words", async () => {
  const statement = "Nothing new to put in the README.";
  const declined: ProjectDocuments = {
    ...DRAFTED,
    drafted: { invocation_id: SECOND.document_id, status: "abstained", statement, version: null },
  };
  renderForm(() => Promise.resolve(declined));

  await userEvent.click(screen.getByRole("button", { name: "Continue drafting" }));

  expect(await screen.findByRole("status")).toHaveTextContent(statement);
});

test("a request the document has moved on from goes to the page, as a decision does", async () => {
  const conflict = new DecisionConflict({
    type: "about:blank",
    title: "The document has moved on",
    detail: "Version 1 is not the latest: version 2 is.",
  });
  const { onStale } = renderForm(() => Promise.reject(conflict));

  await userEvent.click(screen.getByRole("button", { name: "Continue drafting" }));

  expect(onStale).toHaveBeenCalledWith(conflict.message);
});

test("it is not offered on an earlier version or a document no agent drafted", () => {
  const draft = vi.fn<ProjectApi["draft"]>();
  const edited: ProjectDocument = { ...BEFORE, versions: [{ ...FIRST, drafted_by: null }] };
  for (const options of [{ isLatest: false }, { document: edited }]) {
    const { unmount } = renderForm(draft, options);
    expect(screen.queryByRole("button", { name: "Continue drafting" })).toBeNull();
    unmount();
  }
});
