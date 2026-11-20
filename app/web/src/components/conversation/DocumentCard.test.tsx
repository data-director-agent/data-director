import { render, screen } from "@testing-library/react";

import fixture from "../../../fixtures/project-answers.json";
import { ProjectApiContext, type ProjectDocuments, httpProjectApi } from "../../project/api";
import { DocumentCard } from "./DocumentCard";

// A README whose one question has been answered (app/tests/test_document_answers.py), its version
// made a note that asks first (docs/specs/drafting.md).
const ANSWERED = fixture as ProjectDocuments;

describe("DocumentCard", () => {
  it("shows a version that asks first with no preview and a way to write the README", () => {
    const readme = ANSWERED.documents[0];
    const version = readme?.versions[0];
    if (!readme || !version) throw new Error("the fixture has no README");
    const asking = { ...version, stage: "questions" as const };
    const document = { ...readme, versions: [asking] };
    render(
      <ProjectApiContext.Provider value={httpProjectApi}>
        <ul>
          <DocumentCard
            projectId={ANSWERED.project_id}
            drafted={{ document, version: asking, latest: asking }}
            idPrefix="card"
            onAnswered={vi.fn()}
            onWrite={vi.fn()}
          />
        </ul>
      </ProjectApiContext.Provider>,
    );
    expect(screen.getByText("Questions first")).toBeVisible();
    expect(screen.queryByRole("button", { name: /Preview/ })).toBeNull();
    expect(screen.getByRole("button", { name: "Write the README" })).toBeVisible();
  });
});
