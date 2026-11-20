/**
 * A project's documents, a person's decision on each and their answers to a draft's questions,
 * behind one interface so tests can stand in for the server (docs/specs/projects.md,
 * docs/specs/drafting.md).
 *
 * The harness decides and records; the shell sends what the person chose and the SHA-256 of the
 * text it showed them, or the answers they gave, and draws the state the server reads back from
 * the project log. It never names who decided or answered: the server knows who is signed in.
 */

import { sha256 } from "@noble/hashes/sha2.js";
import { bytesToHex, utf8ToBytes } from "@noble/hashes/utils.js";
import { createContext, useContext } from "react";

import type { DocumentQuestion } from "../api/contract";
import type {
  BuiltPackage,
  DeletedProject,
  DepositReview,
  Disclosure,
  DocumentVersion,
  ProjectDetails,
  ProjectDocument,
  ProjectDocuments,
  ProjectIntake,
  ProjectSummary,
  RepositorySearch,
  SavedInventory,
  Validation,
} from "../api/generated/responses";
import type { ProjectProgress, StepMark } from "../flow/types";
import { json } from "../http";
import type { Problem } from "../run/types";
import type { KeepChoice, ResearcherRecord } from "./researcher";

export type { DocumentQuestion } from "../api/contract";
export type {
  BuiltPackage,
  DeletedProject,
  DepositReview,
  Disclosure,
  DocumentVersion,
  IntakeQuestion,
  ProjectDetails,
  ProjectDocument,
  ProjectDocuments,
  ProjectIntake,
  ProjectSummary,
  RepositoryMatch,
  RepositorySearch,
  ReviewItem,
  ReviewRules,
  SavedInventory,
  Validation,
  ValidationResult,
} from "../api/generated/responses";

/** The state of a document's version, as the harness records it. */
export type VersionState = DocumentVersion["state"];
export type Verdict = "approved" | "rejected";
/** What a person decided about a file the deposit check marked. */
export type ItemDecision = "keep" | "leave_out" | "change";

/** One answer as the shell sends it, to a question the latest version asks. */
export interface GivenAnswer {
  answered_question: string;
  answer_text: string;
}

export interface DecisionRequest {
  version: number;
  digest: string;
  decision: Verdict;
  reason?: string;
  edited_text?: string;
}

/**
 * The server would not record the decision because the document has moved on (a `409`), or it
 * is not in the project (a `404`): nothing but the refusal was recorded, and the person must read
 * the latest version and decide again.
 */
export class DecisionConflict extends Error {
  constructor(readonly problem: Problem) {
    super(problem.detail ?? problem.title);
    this.name = "DecisionConflict";
  }
}

/** The harness built no package because the project is not valid: `validation` says why. */
export class PackageRefused extends Error {
  readonly validation: Validation;

  constructor(problem: Problem & { validation: Validation }) {
    super(problem.detail ?? problem.title);
    this.name = "PackageRefused";
    this.validation = problem.validation;
  }
}

/** One field a repository's requirements name, and how much the deposit needs it. */
export interface RequiredField {
  property: string;
  schema_org: string;
  obligation: "required" | "recommended";
  /** What the repository's own deposit form calls it, where an override says. */
  form_label?: string;
  qualifier?: Record<string, string>;
}

/**
 * The requirements a chosen repository resolved to (docs/specs/deposit.md): the repository's
 * override, if the deployment has one, merged on its standard's set. Its name and declared
 * standards came from the pinned re3data export, not from anyone typing them.
 */
export interface RepositoryRequirements {
  re3data_id: string;
  repository_name: string;
  conforms_to: string;
  requirement_sets: { ref: string; sha256: string }[];
  fields: RequiredField[];
  required_documents: string[];
  recommended_documents: string[];
  media_types?: string[];
  licences?: string[];
  max_file_size?: number;
  max_item_size?: number;
  warnings: string[];
  /** What the sets' sources leave open, each naming the issue that will settle it. */
  unconfirmed?: string[];
  /** Where the repository is, from its override; absent without one. */
  repository_url?: string;
  guidance?: string[]; // The pages the sets' values came from, the standard's first.
}

export interface ProjectApi {
  projects(signal?: AbortSignal): Promise<ProjectSummary[]>;
  /** Start a project of the person's own, with no conversation yet, named by `title` if given
   * (`POST /api/projects`, docs/specs/app.md rule 27). */
  create(title?: string): Promise<ProjectSummary>;
  /** Give the project a person's name; a model's name never replaces it. */
  rename(projectId: string, title: string): Promise<ProjectDetails>;
  /** Delete the project, which removes nothing, sending the name the owner typed: its title, or
   * its identifier while it has none (`DELETE /api/projects/{id}`). Answers with its summary. */
  remove(projectId: string, typedName: string): Promise<DeletedProject>;
  /** Restore a deleted project within its restore period (`POST /api/projects/{id}/restore`). */
  restore(projectId: string): Promise<ProjectDetails>;
  /** The deleted projects the person may still restore, the one deleted last first. */
  deletedProjects(signal?: AbortSignal): Promise<DeletedProject[]>;
  documents(projectId: string, signal?: AbortSignal): Promise<ProjectDocuments>;
  disclosure(projectId: string, signal?: AbortSignal): Promise<Disclosure>;
  decide(projectId: string, documentId: string, request: DecisionRequest): Promise<ProjectDocuments>;
  /** Records the person's answers to questions the latest version asks. */
  answer(
    projectId: string,
    documentId: string,
    version: number,
    answers: GivenAnswer[],
  ): Promise<ProjectDocuments>;
  /** The inventory the project holds, as it was added; the inventory dialog reads it. */
  inventory(projectId: string, signal?: AbortSignal): Promise<unknown>;
  /** Adds `inventory` as the project's latest, revising the one it holds; answers with what it then holds. */
  saveInventory(projectId: string, inventory: unknown): Promise<SavedInventory>;
  /** The repository chosen for the project, or null if none has been. */
  repository(projectId: string, signal?: AbortSignal): Promise<RepositoryRequirements | null>;
  /** Where the project is in the process flow, derived anew by the harness. */
  progress(projectId: string, signal?: AbortSignal): Promise<ProjectProgress>;
  /** Record the entry point the researcher chose; answers with the progress derived anew. */
  chooseEntry(projectId: string, entry: number): Promise<ProjectProgress>;
  /** Record a step marked done, skipped or open again; answers with the progress anew. */
  markStep(projectId: string, stepId: string, mark: StepMark): Promise<ProjectProgress>;
  /** Where the project's intake stands, with its next question. */
  intake(projectId: string, signal?: AbortSignal): Promise<ProjectIntake>;
  /** Record the researcher's answer to one intake question; answers with the intake anew. */
  answerIntake(projectId: string, questionId: string, values: string[]): Promise<ProjectIntake>;
  /** Record the intake dismissed; answers with the intake anew. */
  dismissIntake(projectId: string): Promise<ProjectIntake>;
  /** Choose a repository by its re3data identifier; answers with the requirements it resolved
   * to. A change is a new choice, and the last one counts. */
  chooseRepository(projectId: string, re3dataId: string): Promise<RepositoryRequirements>;
  /** Repositories in the pinned re3data export that `query` names by name, re3data identifier,
   * re3data DOI or URL; with an empty `query`, those the deployment suggests. */
  searchRepositories(query: string, signal?: AbortSignal): Promise<RepositorySearch>;
  /** Validates the project against its chosen repository's requirements; the log keeps it. */
  validate(projectId: string): Promise<Validation>;
  /** Validates the project and, if it is valid, builds its deposit package; else `PackageRefused`. */
  buildPackage(projectId: string): Promise<BuiltPackage>;
  /** Record the person's decision on an item the deposit check lists; answers with the review. */
  decideItem(projectId: string, itemId: string, decision: ItemDecision, note?: string): Promise<DepositReview>;
  /** Record the person's confirmation of every statement before deposit; answers with the review. */
  confirmChecks(projectId: string, confirmed: string[]): Promise<DepositReview>;
  /** What the signed-in person's own public ORCID record offers; nothing is kept. */
  orcidRecord(signal?: AbortSignal): Promise<ResearcherRecord>;
  /** The ORCID facts the project's researchers kept, which agents in the project are given. */
  researchers(projectId: string, signal?: AbortSignal): Promise<ResearcherRecord[]>;
  /** Keep what the person ticked of their own record; answers with the project's records. */
  keepResearcher(projectId: string, keep: KeepChoice): Promise<ResearcherRecord[]>;
  /** Stop agents being given what the person kept; answers with the records that stand. */
  withdrawResearcher(projectId: string): Promise<ResearcherRecord[]>;
}

/**
 * The SHA-256 of `text` as UTF-8, in hex: how a decision names the text that was shown. It is
 * computed in JavaScript rather than with Web Crypto, which a browser offers only in a secure
 * context, so that deciding works however the shell is served.
 */
export function digestOf(text: string): string {
  return bytesToHex(sha256(utf8ToBytes(text)));
}

const PACKAGE_REFUSED = "/package-refused";

/** A response's body, or its error, with a refused package and a stale decision raised as such. */
function parse<T>(response: Response): Promise<T> {
  return json<T>(response, (status, found) => {
    const problem = found as (Problem & { validation?: Validation }) | null;
    if (problem?.validation && problem.type.endsWith(PACKAGE_REFUSED)) {
      return new PackageRefused({ ...problem, validation: problem.validation });
    }
    if (problem && (status === 409 || status === 404)) return new DecisionConflict(problem);
    return null;
  });
}

function projectPath(projectId: string): string {
  return `/api/projects/${encodeURIComponent(projectId)}`;
}

function progressPath(projectId: string): string {
  return `${projectPath(projectId)}/progress`;
}

function post(body: unknown): RequestInit {
  return { ...put(body), method: "POST" };
}

function put(body: unknown): RequestInit {
  return { ...bodiless("PUT"), body: JSON.stringify(body) };
}

/** A request that changes state with no body, which the server still takes only as JSON (#728). */
function bodiless(method: string): RequestInit {
  return { method, headers: { "content-type": "application/json" } };
}

function documentsPath(projectId: string): string {
  return `${projectPath(projectId)}/documents`;
}

export const httpProjectApi: ProjectApi = {
  async projects(signal) {
    return parse(await fetch("/api/projects", signal ? { signal } : {}));
  },
  async create(title) {
    return parse(await fetch("/api/projects", post(title ? { title } : {})));
  },
  async rename(projectId, title) {
    return parse(await fetch(`${projectPath(projectId)}/title`, put({ title })));
  },
  async remove(projectId, typedName) {
    return parse(
      await fetch(projectPath(projectId), { ...put({ title: typedName }), method: "DELETE" }),
    );
  },
  async restore(projectId) {
    return parse(await fetch(`${projectPath(projectId)}/restore`, post({})));
  },
  async deletedProjects(signal) {
    return parse(await fetch("/api/projects/deleted", signal ? { signal } : {}));
  },
  async documents(projectId, signal) {
    return parse(await fetch(documentsPath(projectId), signal ? { signal } : {}));
  },
  async disclosure(projectId, signal) {
    return parse(
      await fetch(
        `/api/projects/${encodeURIComponent(projectId)}/disclosure`,
        signal ? { signal } : {},
      ),
    );
  },
  async inventory(projectId, signal) {
    return parse(
      await fetch(
        `/api/projects/${encodeURIComponent(projectId)}/inventory`,
        signal ? { signal } : {},
      ),
    );
  },
  async saveInventory(projectId, inventory) {
    return parse(await fetch(`${projectPath(projectId)}/inventory`, post({ inventory })));
  },
  async repository(projectId, signal) {
    const response = await fetch(`${projectPath(projectId)}/repository`, signal ? { signal } : {});
    if (response.status === 404) {
      const problem = (await response.clone().json().catch(() => null)) as Problem | null;
      if (problem?.type?.endsWith("/repository-not-chosen")) return null;
    }
    return parse(response);
  },
  async progress(projectId, signal) {
    return parse(await fetch(progressPath(projectId), signal ? { signal } : {}));
  },
  async chooseEntry(projectId, entry) {
    return parse(await fetch(`${progressPath(projectId)}/entry`, put({ entry })));
  },
  async markStep(projectId, stepId, mark) {
    return parse(
      await fetch(`${progressPath(projectId)}/steps/${encodeURIComponent(stepId)}`, put({ mark })),
    );
  },
  async intake(projectId, signal) {
    return parse(await fetch(`${projectPath(projectId)}/intake`, signal ? { signal } : {}));
  },
  async answerIntake(projectId, questionId, values) {
    return parse(
      await fetch(
        `${projectPath(projectId)}/intake/${encodeURIComponent(questionId)}`,
        post({ answer_values: values }),
      ),
    );
  },
  async dismissIntake(projectId) {
    return parse(await fetch(`${projectPath(projectId)}/intake/dismiss`, post({})));
  },
  async chooseRepository(projectId, re3dataId) {
    return parse(
      await fetch(
        `${projectPath(projectId)}/repository`,
        put({ re3data_id: re3dataId }),
      ),
    );
  },
  async searchRepositories(query, signal) {
    const params = new URLSearchParams();
    if (query.trim()) params.set("q", query.trim());
    const search = params.size > 0 ? `?${params.toString()}` : "";
    return parse(await fetch(`/api/repositories${search}`, signal ? { signal } : {}));
  },
  async validate(projectId) {
    return parse(await fetch(`${projectPath(projectId)}/validation`, bodiless("POST")));
  },
  async buildPackage(projectId) {
    return parse(await fetch(`${projectPath(projectId)}/package`, bodiless("POST")));
  },
  async decideItem(projectId, itemId, decision, note) {
    const path = `${projectPath(projectId)}/review/items/${encodeURIComponent(itemId)}`;
    return parse(await fetch(path, put(note ? { decision, note } : { decision })));
  },
  async confirmChecks(projectId, confirmed) {
    return parse(await fetch(`${projectPath(projectId)}/review/confirmation`, put({ confirmed })));
  },
  async orcidRecord(signal) {
    return parse(await fetch("/api/researcher/orcid", signal ? { signal } : {}));
  },
  async researchers(projectId, signal) {
    return parse(await fetch(`${projectPath(projectId)}/researchers`, signal ? { signal } : {}));
  },
  async keepResearcher(projectId, keep) {
    return parse(await fetch(`${projectPath(projectId)}/researchers/me`, put({ keep })));
  },
  async withdrawResearcher(projectId) {
    return parse(await fetch(`${projectPath(projectId)}/researchers/me`, bodiless("DELETE")));
  },
  async decide(projectId, documentId, request) {
    return parse(
      await fetch(
        `${documentsPath(projectId)}/${encodeURIComponent(documentId)}/decisions`,
        post(request),
      ),
    );
  },
  async answer(projectId, documentId, version, answers) {
    return parse(
      await fetch(
        `${documentsPath(projectId)}/${encodeURIComponent(documentId)}/answers`,
        post({ version, answers }),
      ),
    );
  },
};

/** The questions of `version` that no answer recorded for `document` has answered yet. */
export function openQuestions(document: ProjectDocument, version: DocumentVersion): DocumentQuestion[] {
  const answered = new Set(document.answers.map((a) => a.question_id));
  return version.questions.filter((q) => !answered.has(q.question_id));
}

/** What a question fills, in words: a README section or one part of it, a data dictionary cell, or a record value. */
export function questionTarget(question: DocumentQuestion): string {
  if (question.gap_property) return `Property “${question.gap_property}”`;
  if (question.gap_section) return `Section “${question.gap_section}”${question.gap_part ? ` › ${question.gap_part}` : ""}`;
  return `${question.gap_file ?? ""} › ${question.gap_field ?? ""} › ${question.gap_column ?? ""}`;
}

export const ProjectApiContext = createContext<ProjectApi>(httpProjectApi);

export function useProjectApi(): ProjectApi {
  return useContext(ProjectApiContext);
}
