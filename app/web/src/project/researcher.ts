/**
 * What a researcher's public ORCID record offers, and what they keep of it in a project
 * (docs/specs/projects.md), as the core contract's `ResearcherRecord` holds it. The app sends the
 * contract's record as it is, so these are typed by hand rather than generated; the fixtures'
 * type check (`../fixtures.typecheck.ts`) holds them to what the server sends.
 */

/** An identifier from another scheme, as an ORCID record gives it, such as a DOI. */
export interface ExternalIdentifier {
  identifier_type: string;
  identifier_value: string;
  identifier_url?: string;
}

export interface Affiliation {
  put_code: string;
  affiliation_kind: string;
  organisation_name: string;
  organisation_identifier?: string;
  organisation_identifier_scheme?: string;
  department?: string;
  role_title?: string;
  start_year?: number;
  end_year?: number;
}

export interface ResearcherWork {
  put_code: string;
  work_title: string;
  work_type?: string;
  publication_year?: number;
  journal_title?: string;
  work_identifiers?: ExternalIdentifier[];
}

export interface ResearcherFunding {
  put_code: string;
  funding_title: string;
  funding_type?: string;
  funder_name: string;
  funder_identifier?: string;
  funder_identifier_scheme?: string;
  award_identifier?: string;
  start_year?: number;
  end_year?: number;
}

/**
 * What a researcher's public ORCID record offers, or what they kept of it in a project
 * (docs/specs/projects.md). Never an email address.
 */
export interface ResearcherRecord {
  orcid_id: string;
  researcher_name?: string;
  other_names?: string[];
  biography?: string;
  keywords?: string[];
  country?: string[];
  researcher_links?: { link_title?: string; link_url: string }[];
  external_identifiers?: ExternalIdentifier[];
  affiliations?: Affiliation[];
  works?: ResearcherWork[];
  works_omitted?: number;
  fundings?: ResearcherFunding[];
  record_retrieved_at: string;
  record_source: string;
}

/** The sections of a record kept whole, and those chosen item by item, by put-code. */
export const RECORD_SECTIONS = [
  "researcher_name",
  "other_names",
  "biography",
  "keywords",
  "country",
  "researcher_links",
  "external_identifiers",
] as const;
export type RecordSection = (typeof RECORD_SECTIONS)[number];
export const RECORD_ITEMS = ["affiliations", "works", "fundings"] as const;
export type RecordItems = (typeof RECORD_ITEMS)[number];

/** What a person ticked: never the facts, which the server reads from ORCID again. */
export interface KeepChoice {
  sections: RecordSection[];
  affiliations: string[];
  works: string[];
  fundings: string[];
}
