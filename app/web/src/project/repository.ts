/**
 * The requirements a chosen repository resolved to, as the project's repository page and the
 * deposit check read them (docs/specs/deposit.md). `api.ts` re-exports them with the rest of what
 * the shell reads of a project.
 */

/** One field a repository's requirements name, and how much the deposit needs it. */
interface RequiredField {
  property: string;
  schema_org: string;
  obligation: "required" | "recommended";
  /** What the repository's own deposit form calls it, where an override says. */
  form_label?: string;
  qualifier?: Record<string, string>;
}

/**
 * The requirements a chosen repository resolved to (docs/specs/deposit.md): its override, if any,
 * merged on its standard's set. Its name and declared standards came from the pinned registry
 * (re3data's, or DataCite's for one re3data does not list), not from anyone typing them.
 */
export interface RepositoryRequirements {
  repository_id: string;
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
