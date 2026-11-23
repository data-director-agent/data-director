/**
 * A project API for the project pages' tests, answering from the fixtures the server's own tests
 * write (`app/web/fixtures`), with any method replaced by the test that is about it.
 */

import disclosureFixture from "../../fixtures/project-disclosure.json";
import fixture from "../../fixtures/project-documents.json";
import repositoryFixture from "../../fixtures/repository-chosen.json";
import suggestedFixture from "../../fixtures/repositories-suggested.json";
import type {
  Disclosure,
  ProjectApi,
  ProjectDocuments,
  RepositoryRequirements,
  RepositorySearch,
} from "../project/api";
import { projectDetails, projectProgress } from "./api";

// What the server says (app/tests/test_document_decisions.py): a README proposed, and a data
// dictionary already approved.
export const PROJECT = fixture as ProjectDocuments;
// The disclosure the server gives (app/tests/test_document_decisions.py): a README a model drafted
// and a person approved as it stood, and a metadata record awaiting a decision.
export const DISCLOSURE = disclosureFixture as Disclosure;
// ORDA, chosen by its re3data identifier (app/tests/test_repository_choice.py).
export const REPOSITORY = repositoryFixture as RepositoryRequirements;
// ORDA and Zenodo, suggested before a search (app/tests/test_repository_search.py).
export const SUGGESTED = suggestedFixture as RepositorySearch;

export function at<T>(items: T[], index: number): T {
  const item = items[index];
  if (item === undefined) throw new Error(`the fixture has no item ${index}`);
  return item;
}

export const README = at(PROJECT.documents, 0);
export const DICTIONARY = at(PROJECT.documents, 1);
export const DRAFT = at(README.versions, 0);

/** `PROJECT` after the README's version 1 is given `state`, as the server would answer. */
export function decided(state: "approved" | "rejected", reason: string | null = null): ProjectDocuments {
  const decision = { reason, decided_by: DRAFT.added_by, decided_at: DRAFT.added_at };
  return {
    ...PROJECT,
    documents: [{ ...README, versions: [{ ...DRAFT, state, decision }] }, DICTIONARY],
    decided: { document_id: README.document_id, version: 1 },
  };
}

export function fakeProjectApi(overrides: Partial<ProjectApi> = {}): ProjectApi {
  return {
    projects: () => Promise.resolve([]),
    create: () => Promise.reject(new Error("no project created in these tests")),
    rename: () => Promise.resolve(projectDetails()),
    remove: () => Promise.reject(new Error("no project deleted in these tests")),
    restore: () => Promise.reject(new Error("no project restored in these tests")),
    deletedProjects: () => Promise.resolve([]),
    documents: () => Promise.resolve(PROJECT),
    disclosure: () => Promise.resolve(DISCLOSURE),
    decide: () => Promise.resolve(decided("approved")),
    answer: () => Promise.resolve(PROJECT),
    revise: () => Promise.reject(new Error("no changes asked for in this test")),
    draft: () => Promise.reject(new Error("no new draft asked for in this test")),
    inventory: () => Promise.resolve(null),
    saveInventory: () => Promise.reject(new Error("not saved in this test")),
    documentation: () => Promise.resolve([]),
    attachDocument: () => Promise.reject(new Error("no document attached in this test")),
    documentationText: () => Promise.reject(new Error("no document read in this test")),
    repository: () => Promise.resolve(REPOSITORY),
    progress: () => Promise.resolve(projectProgress()),
    chooseEntry: () => Promise.resolve(projectProgress()),
    markStep: () => Promise.resolve(projectProgress()),
    intake: () => Promise.reject(new Error("no intake in these tests")),
    answerIntake: () => Promise.reject(new Error("no intake in these tests")),
    dismissIntake: () => Promise.reject(new Error("no intake in these tests")),
    validate: () => Promise.reject(new Error("not checked in this test")),
    buildPackage: () => Promise.reject(new Error("not built in this test")),
    decideItem: () => Promise.reject(new Error("nothing decided in this test")),
    confirmChecks: () => Promise.reject(new Error("nothing confirmed in this test")),
    chooseRepository: () => Promise.reject(new Error("no repository in these tests")),
    searchRepositories: () => Promise.resolve(SUGGESTED),
    orcidRecord: () => Promise.reject(new Error("no ORCID record in these tests")),
    researchers: () => Promise.resolve([]),
    keepResearcher: () => Promise.reject(new Error("nothing kept in these tests")),
    withdrawResearcher: () => Promise.resolve([]),
    ...overrides,
  };
}
