import fixture from "../../fixtures/project-documents.json";
import type { DocumentVersion, ProjectDocument, ProjectDocuments } from "./api";
import { documentHref, draftedBy, latestOf } from "./drafted";

const PROJECT = fixture as ProjectDocuments;
const README = PROJECT.documents[0] as ProjectDocument;
const DRAFT = README.versions[0] as DocumentVersion;
const DRAFTER = DRAFT.drafted_by?.invocation_id ?? "";

describe("draftedBy", () => {
  it("finds the version a run drafted, beside its document's latest version", () => {
    const found = draftedBy([DRAFTER], PROJECT.documents);
    expect(found).toHaveLength(1);
    expect(found[0]?.document.document_id).toBe(README.document_id);
    expect(found[0]?.version).toBe(DRAFT);
    expect(found[0]?.latest).toBe(DRAFT);
  });

  it("finds nothing for a run that drafted no project document", () => {
    expect(draftedBy(["not-a-drafter"], PROJECT.documents)).toEqual([]);
    expect(draftedBy([], PROJECT.documents)).toEqual([]);
  });

  it("matches any of several runs, and says when a later version has replaced the draft", () => {
    const edit: DocumentVersion = { ...DRAFT, version: 2, drafted_by: null, state: "proposed" };
    const second: DocumentVersion = {
      ...DRAFT,
      version: 3,
      drafted_by: { ...(DRAFT.drafted_by as NonNullable<DocumentVersion["drafted_by"]>), invocation_id: "later" },
    };
    const documents = [{ ...README, versions: [DRAFT, edit, second] }];
    const found = draftedBy(["child", DRAFTER, "later"], documents);
    expect(found.map((f) => f.version.version)).toEqual([1, 3]);
    expect(found.every((f) => f.latest.version === 3)).toBe(true);
  });

  it("skips a document with no versions", () => {
    expect(draftedBy([DRAFTER], [{ ...README, versions: [] }])).toEqual([]);
    expect(latestOf({ ...README, versions: [] })).toBeUndefined();
  });
});

describe("documentHref", () => {
  it("links to the document open in the project's reader", () => {
    expect(documentHref("p/1", "d 1")).toBe("/projects/p%2F1?doc=d%201");
  });
});
