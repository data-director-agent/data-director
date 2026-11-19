/**
 * Responses as the server sends them, for the shell's tests to change one field of: each has
 * every field the generated type requires (`../api/generated/responses.ts`), set to what an
 * empty or fresh thing has, so that a test names only what it is about.
 */

import type {
  About,
  ConversationSummary,
  ProjectDetails,
  ProjectProgress,
  ProjectSummary,
  SavedInventory,
} from "../api/generated/responses";

/** A project with no entry point, nothing started and nothing suggested. */
export function projectProgress(over: Partial<ProjectProgress> = {}): ProjectProgress {
  return { entry: null, entry_source: null, steps: {}, reasons: {}, suggested: null, decisions: [], ...over };
}

/** A project just created by the reference researcher, with nothing in it. */
export function projectDetails(over: Partial<ProjectDetails> = {}): ProjectDetails {
  return {
    project_id: "p1",
    title: null,
    title_source: null,
    created_at: "2026-01-01T00:00:00Z",
    created_by: {
      principal_id: "https://orcid.org/0000-0002-1825-0097",
      name: "Josiah Carberry",
      principal_kind: "person",
      assurance: "asserted",
    },
    inventory: null,
    repository: null,
    documents: { proposed: 0, approved: 0, rejected: 0 },
    conversation_count: 0,
    intake: "pending",
    deleted: null,
    restore_days: 30,
    progress: projectProgress(),
    ...over,
  };
}

/** `projectDetails` as the projects list gives it, with no conversation. */
export function projectSummary(over: Partial<ProjectSummary> = {}): ProjectSummary {
  return { ...projectDetails(), conversations: [], ...over };
}

/** A conversation of one turn that succeeded, started in no project. */
export function conversationSummary(over: Partial<ConversationSummary> = {}): ConversationSummary {
  return {
    conversation_id: "c1",
    project_id: null,
    agent_id: "orchestrator.model",
    first_invocation_id: "i1",
    title: "Depositing a soil survey",
    title_source: "model",
    turns: 1,
    started_at: "2026-01-01T09:30:00Z",
    last_completed_at: "2026-01-01T09:31:00Z",
    last_status: "succeeded",
    ...over,
  };
}

/** An inventory a project holds, made of one part and revising none. */
export function savedInventory(over: Partial<SavedInventory> = {}): SavedInventory {
  return {
    digest: "a".repeat(64),
    file_count: 1,
    inventory_made_at: "2026-11-01T09:00:00Z",
    added_at: "2026-11-01T09:05:00Z",
    revises: null,
    part_count: null,
    ...over,
  };
}

/** A build that takes no problem reports and describes no folder on its own machine. */
export function about(over: Partial<About> = {}): About {
  return {
    app_version: "0.3.0",
    harness_version: "0.3.0",
    commit: "abc1234def",
    feedback_enabled: false,
    privacy_notice_url: null,
    server_folders: false,
    incompatible: [],
    unavailable: [],
    profile: { id: "reference", version: 1, digest: "d".repeat(64), orchestrator: null },
    ...over,
  };
}
