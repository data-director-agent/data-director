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

import type { ProjectProgress, StepMark } from "../flow/types";
import { RunRefused } from "../run/api";
import type { Problem } from "../run/types";
import { checkSignedIn } from "../session/api";

export type VersionState = "proposed" | "approved" | "rejected";
export type Verdict = "approved" | "rejected";

export interface RecordedPrincipal {
  principal_id: string;
  name: string;
  assurance: string;
  vouched_by?: string;
}

/** A drafter's question about one gap: a README section, or a data dictionary cell. */
export interface DocumentQuestion {
  question_id: string;
  question_prompt: string;
  gap_section?: string;
  gap_file?: string;
  gap_field?: string;
  gap_column?: string;
}

export interface DocumentVersion {
  document_id: string;
  document_kind: string;
  version: number;
  digest: string;
  media_type: string;
  document_title: string | null;
  conforms_to: string | null;
  revises: { document_id: string; version: number } | null;
  /** The run that drafted it; null for a person's edit. */
  drafted_by: {
    agent_id: string;
    agent_version: string;
    invocation_id: string;
    document_derivation: string;
  } | null;
  /** What the version asks the researcher, one question per gap (docs/specs/drafting.md). */
  questions: DocumentQuestion[];
  added_by: RecordedPrincipal;
  added_at: string;
  state: VersionState;
  decision: { reason: string | null; decided_by: RecordedPrincipal; decided_at: string } | null;
  text: string;
}

/** A person's answer to one question, as the project log records it: the latest stands. */
export interface RecordedAnswer {
  question_id: string;
  answer_text: string;
  /** The version whose question it answered. */
  version: number;
  answered_by: RecordedPrincipal;
  answered_at: string;
}

export interface ProjectDocument {
  document_id: string;
  document_kind: string;
  document_title: string | null;
  versions: DocumentVersion[];
  /** The answers given to its questions, which the next draft places as supplied. */
  answers?: RecordedAnswer[];
}

/** One answer as the shell sends it, to a question the latest version asks. */
export interface GivenAnswer {
  answered_question: string;
  answer_text: string;
}

/** The harness's rule for when a decision needs a reason, which the form states. */
export interface ReviewRules {
  reason_required: { approved: boolean; edited_and_approved: boolean; rejected: boolean };
  reason_max_length: number;
}

export interface ProjectDocuments {
  project_id: string;
  documents: ProjectDocument[];
  review: ReviewRules;
  /** The longest answer the harness keeps, in characters. */
  answer_max_length?: number;
  /** After a decision: the version it decided. */
  decided?: { document_id: string; version: number };
  /** After answers: the version whose questions they answered. */
  answered?: { document_id: string; version: number };
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

/** One approved version, as the harness's disclosure describes it (docs/specs/disclosure.md). */
export interface DisclosedDocument {
  document_id: string;
  document_kind: string;
  document_title: string | null;
  version: number;
  digest: string;
  origin: "model" | "model_revised" | "template" | "template_revised" | "person";
  draft: {
    agent_id: string;
    agent_version: string;
    invocation_id: string;
    derivation: string;
    completed_at: string | null;
    models: { provider: string; model_id: string; called_at: string; prompt_digest: string | null }[];
  } | null;
  edited_by: string[];
  approved_by: string;
  approved_at: string;
  reason: string | null;
}

/**
 * What a project's approved documents owe to generative AI: the harness's statement, in Markdown,
 * and the same account as a PROV-O graph in JSON-LD. The shell shows and offers them as they are.
 */
export interface Disclosure {
  project_id: string;
  made_at: string;
  pending: number;
  statement: string;
  documents: DisclosedDocument[];
  prov: Record<string, unknown>;
}

/** A conversation started in a project, as the projects list names it. */
export interface ProjectConversation {
  conversation_id: string;
  title: string;
  started_at: string;
  last_completed_at?: string | null;
  turns: number;
}

/** The repository a project chose last, as its summary names it. */
export interface ChosenRepository {
  re3data_id: string;
  repository_name: string;
  /** What the choice does not check, for example that re3data does not list DataCite for it. */
  warnings: string[];
  chosen_at: string;
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
}

/**
 * One project the person may read, as `GET /api/projects` lists it: what it holds, how many of
 * its documents are in each state, and the conversations started in it, most recent first.
 */
export interface ProjectSummary {
  project_id: string;
  /** The app starts projects untitled, so this is usually null. */
  title: string | null;
  created_at: string;
  created_by: RecordedPrincipal;
  inventory: { digest: string; file_count: number; inventory_made_at: string; added_at: string } | null;
  repository: ChosenRepository | null;
  documents: Record<VersionState, number>;
  conversations: ProjectConversation[];
}

export interface ProjectApi {
  projects(signal?: AbortSignal): Promise<ProjectSummary[]>;
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
  /** Where the project is in the process flow, derived anew by the harness. */
  progress(projectId: string, signal?: AbortSignal): Promise<ProjectProgress>;
  /** Record the entry point the researcher chose; answers with the progress derived anew. */
  chooseEntry(projectId: string, entry: number): Promise<ProjectProgress>;
  /** Record a step marked done, skipped or open again; answers with the progress anew. */
  markStep(projectId: string, stepId: string, mark: StepMark): Promise<ProjectProgress>;
  /** Choose a repository by its re3data identifier; answers with the requirements it resolved
   * to. A change is a new choice, and the last one counts. */
  chooseRepository(projectId: string, re3dataId: string): Promise<RepositoryRequirements>;
}

/**
 * The SHA-256 of `text` as UTF-8, in hex: how a decision names the text that was shown. It is
 * computed in JavaScript rather than with Web Crypto, which a browser offers only in a secure
 * context, so that deciding works however the shell is served.
 */
export function digestOf(text: string): string {
  return bytesToHex(sha256(utf8ToBytes(text)));
}

async function json<T>(response: Response): Promise<T> {
  if (response.ok) return (await response.json()) as T;
  checkSignedIn(response);
  const problem = (await response.json().catch(() => null)) as Problem | null;
  if (problem && (response.status === 409 || response.status === 404)) {
    throw new DecisionConflict(problem);
  }
  if (response.status === 400 && problem) throw new RunRefused(problem);
  throw new Error(problem?.detail ?? `the server answered ${response.status}`);
}

function progressPath(projectId: string): string {
  return `/api/projects/${encodeURIComponent(projectId)}/progress`;
}

function put(body: unknown): RequestInit {
  return {
    method: "PUT",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  };
}

function documentsPath(projectId: string): string {
  return `/api/projects/${encodeURIComponent(projectId)}/documents`;
}

export const httpProjectApi: ProjectApi = {
  async projects(signal) {
    return json(await fetch("/api/projects", signal ? { signal } : {}));
  },
  async documents(projectId, signal) {
    return json(await fetch(documentsPath(projectId), signal ? { signal } : {}));
  },
  async disclosure(projectId, signal) {
    return json(
      await fetch(
        `/api/projects/${encodeURIComponent(projectId)}/disclosure`,
        signal ? { signal } : {},
      ),
    );
  },
  async inventory(projectId, signal) {
    return json(
      await fetch(
        `/api/projects/${encodeURIComponent(projectId)}/inventory`,
        signal ? { signal } : {},
      ),
    );
  },
  async progress(projectId, signal) {
    return json(await fetch(progressPath(projectId), signal ? { signal } : {}));
  },
  async chooseEntry(projectId, entry) {
    return json(await fetch(`${progressPath(projectId)}/entry`, put({ entry })));
  },
  async markStep(projectId, stepId, mark) {
    return json(
      await fetch(`${progressPath(projectId)}/steps/${encodeURIComponent(stepId)}`, put({ mark })),
    );
  },
  async chooseRepository(projectId, re3dataId) {
    return json(
      await fetch(
        `/api/projects/${encodeURIComponent(projectId)}/repository`,
        put({ re3data_id: re3dataId }),
      ),
    );
  },
  async decide(projectId, documentId, request) {
    return json(
      await fetch(`${documentsPath(projectId)}/${encodeURIComponent(documentId)}/decisions`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(request),
      }),
    );
  },
  async answer(projectId, documentId, version, answers) {
    return json(
      await fetch(`${documentsPath(projectId)}/${encodeURIComponent(documentId)}/answers`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ version, answers }),
      }),
    );
  },
};

/** The questions of `version` that no answer recorded for `document` has answered yet. */
export function openQuestions(document: ProjectDocument, version: DocumentVersion): DocumentQuestion[] {
  const answered = new Set((document.answers ?? []).map((a) => a.question_id));
  return version.questions.filter((q) => !answered.has(q.question_id));
}

/** What a question fills, in words: a README section, or a data dictionary cell. */
export function questionTarget(question: DocumentQuestion): string {
  if (question.gap_section) return `Section “${question.gap_section}”`;
  return `${question.gap_file ?? ""} › ${question.gap_field ?? ""} › ${question.gap_column ?? ""}`;
}

export const ProjectApiContext = createContext<ProjectApi>(httpProjectApi);

export function useProjectApi(): ProjectApi {
  return useContext(ProjectApiContext);
}
