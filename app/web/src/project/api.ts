/**
 * A project's documents and a person's decision on each, behind one interface so tests can stand
 * in for the server (docs/specs/projects.md).
 *
 * The harness decides and records; the shell sends what the person chose and the SHA-256 of the
 * text it showed them, and draws the state the server reads back from the project log. It never
 * names who decided: the server knows who is signed in.
 */

import { sha256 } from "@noble/hashes/sha2.js";
import { bytesToHex, utf8ToBytes } from "@noble/hashes/utils.js";
import { createContext, useContext } from "react";

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
  added_by: RecordedPrincipal;
  added_at: string;
  state: VersionState;
  decision: { reason: string | null; decided_by: RecordedPrincipal; decided_at: string } | null;
  text: string;
}

export interface ProjectDocument {
  document_id: string;
  document_kind: string;
  document_title: string | null;
  versions: DocumentVersion[];
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
  /** After a decision: the version it decided. */
  decided?: { document_id: string; version: number };
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
  repository: { re3data_id: string; repository_name: string; chosen_at: string } | null;
  documents: Record<VersionState, number>;
  conversations: ProjectConversation[];
}

export interface ProjectApi {
  projects(signal?: AbortSignal): Promise<ProjectSummary[]>;
  documents(projectId: string, signal?: AbortSignal): Promise<ProjectDocuments>;
  disclosure(projectId: string, signal?: AbortSignal): Promise<Disclosure>;
  decide(projectId: string, documentId: string, request: DecisionRequest): Promise<ProjectDocuments>;
  /** The inventory the project holds, as it was added; the inventory dialog reads it. */
  inventory(projectId: string, signal?: AbortSignal): Promise<unknown>;
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
  async decide(projectId, documentId, request) {
    return json(
      await fetch(`${documentsPath(projectId)}/${encodeURIComponent(documentId)}/decisions`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(request),
      }),
    );
  },
};

export const ProjectApiContext = createContext<ProjectApi>(httpProjectApi);

export function useProjectApi(): ProjectApi {
  return useContext(ProjectApiContext);
}
