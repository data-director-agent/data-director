import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";

import fixture from "../../../fixtures/project-revised.json";
import {
  DecisionConflict,
  type DocumentVersion,
  type ProjectApi,
  ProjectApiContext,
  type ProjectDocuments,
  digestOf,
  httpProjectApi,
} from "../../project/api";
import { RevisionRequest } from "./RevisionRequest";

// What the server says after a request for changes (app/tests/test_document_revisions.py): a
// README's version 1, with the change asked of it, and version 2, which revises it.
const REVISED = fixture as ProjectDocuments;
const README = REVISED.documents[0];
if (!README) throw new Error("the fixture has no document");
const [first, second] = README.versions;
if (!first || !second) throw new Error("the fixture has no revision");
const FIRST: DocumentVersion = first;
const SECOND: DocumentVersion = second;
const ASKED = FIRST.revision_request?.instruction ?? "";

function renderForm(
  revise: ProjectApi["revise"],
  version: DocumentVersion = FIRST,
  { kind = "readme", isLatest = true }: { kind?: string; isLatest?: boolean } = {},
) {
  const onRevised = vi.fn();
  const onStale = vi.fn(() => Promise.resolve());
  const view = render(
    <ProjectApiContext.Provider value={{ ...httpProjectApi, revise }}>
      <RevisionRequest
        projectId={REVISED.project_id}
        name="README"
        kind={kind}
        version={version}
        isLatest={isLatest}
        maxLength={REVISED.request_max_length}
        onRevised={onRevised}
        onStale={onStale}
      />
    </ProjectApiContext.Provider>,
  );
  return { ...view, onRevised, onStale };
}

test("a request names the version and the text shown, and says which version revises it", async () => {
  const revise = vi.fn<ProjectApi["revise"]>(() => Promise.resolve(REVISED));
  const { container, onRevised } = renderForm(revise);
  expect(await axe(container)).toHaveNoViolations();

  await userEvent.type(screen.getByLabelText("What to change in the README"), ASKED);
  await userEvent.click(screen.getByRole("button", { name: "Ask for changes" }));

  expect(revise).toHaveBeenCalledWith(REVISED.project_id, FIRST.document_id, {
    version: FIRST.version,
    digest: digestOf(FIRST.text),
    instruction: ASKED,
  });
  expect(onRevised).toHaveBeenCalledWith(REVISED);
  expect(await screen.findByRole("status")).toHaveTextContent(`Version ${SECOND.version}`);
});

test("when the agent drafts no version, the status says why in its words", async () => {
  const statement = "The README was not changed: the model found no change it could make.";
  const declined: ProjectDocuments = {
    ...REVISED,
    revised: { invocation_id: SECOND.document_id, status: "abstained", statement, version: null },
  };
  renderForm(() => Promise.resolve(declined));

  await userEvent.type(screen.getByLabelText("What to change in the README"), ASKED);
  await userEvent.click(screen.getByRole("button", { name: "Ask for changes" }));

  expect(await screen.findByRole("status")).toHaveTextContent(statement);
  expect(screen.getByLabelText("What to change in the README")).toHaveValue(ASKED);
});

test("a request the document has moved on from goes to the page, as a decision does", async () => {
  const conflict = new DecisionConflict({
    type: "about:blank",
    title: "The document has moved on",
    detail: "Version 1 is not the latest: version 2 is.",
  });
  const { onStale } = renderForm(() => Promise.reject(conflict));

  await userEvent.type(screen.getByLabelText("What to change in the README"), ASKED);
  await userEvent.click(screen.getByRole("button", { name: "Ask for changes" }));

  expect(onStale).toHaveBeenCalledWith(conflict.message);
});

test("only a README's latest draft can be revised", () => {
  const revise = vi.fn<ProjectApi["revise"]>();
  const asking: DocumentVersion = { ...SECOND, stage: "questions" };
  for (const [version, options] of [
    [SECOND, { kind: "data_dictionary" }],
    [FIRST, { isLatest: false }],
    [asking, {}],
  ] as const) {
    const { unmount } = renderForm(revise, version, options);
    expect(screen.queryByRole("button", { name: "Ask for changes" })).toBeNull();
    unmount();
  }
});
