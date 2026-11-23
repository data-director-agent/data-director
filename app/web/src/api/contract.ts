/**
 * The core contract's classes (`dd_sdk.contract`) that the app's responses carry, as the shell
 * reads them. The response models name each by its `tsType` (app/src/dd_app/contract_shapes.py),
 * and `generated/responses.ts` imports it from here, so that the generated interfaces use these
 * rather than an untyped object. The contract's other classes that the shell reads are typed beside their
 * use (`Question`, `ProjectFact`) or in `@data-director/agent-view` (`Envelope`).
 */

/** Whom a change acted for, as the project log records it (the contract's `Principal`). */
export interface Principal {
  /** An absolute IRI for the person or role; an ORCID iD for a person where one exists. */
  principal_id: string;
  name: string;
  principal_kind?: "person" | "accountable_role";
  assurance: "asserted" | "authenticated";
  /** The issuer that vouched: present when authenticated, absent when asserted. */
  vouched_by?: string;
}

/** One version of a project document, numbered from 1 within it. */
export interface DocumentVersionRef {
  document_id: string;
  version: number;
}

/** A drafter's question about one gap: a README section, a data dictionary cell, or a metadata record value. */
export interface DocumentQuestion {
  question_id: string;
  question_prompt: string;
  /** A line of help shown under the question. */
  question_help?: string;
  /** How the question is answered: `text` (the default), or `list`, a list of values. */
  answer_kind?: "text" | "list";
  gap_section?: string;
  gap_part?: string;
  gap_file?: string;
  gap_field?: string;
  gap_column?: string;
  /** Every file whose cell the answer fills, `gap_file` among them, when the column is one several files share. */
  gap_files?: string[];
  gap_property?: string;
  /** A drafter's suggested answer, offered beside the question and never put into the draft. */
  suggested_answer?: string;
  /** How the suggestion came about, such as `model`, or `answer` for a person's own words. */
  suggestion_derivation?: string;
  /** The value the question asks for that every kind of document gives the same way. */
  shared_field?: string;
  /** Where a suggestion derived as `answer` came from: a document kind, or `decision`. */
  suggested_from?: string;
}

/** The request a run was started with, as the run store keeps it. */
export interface InvocationRequest {
  invocation_id: string;
  agent_id: string;
  issued_at: string;
  requirement_ids?: string[] | null;
  conversation_id?: string | null;
  project_id?: string | null;
  parent_invocation_id?: string | null;
  /** An instance of an input class the agent accepts, named by `schema_class`. */
  input: { schema_class: string; [key: string]: unknown };
}
