/** How the Researchers panel names and reads the sections of a kept ORCID record. */

import {
  type KeepChoice,
  RECORD_SECTIONS,
  type RecordItems,
  type RecordSection,
  type ResearcherRecord,
} from "../../project/researcher";

export const SECTION_LABELS: Record<RecordSection, string> = {
  researcher_name: "Name",
  other_names: "Other names",
  biography: "Biography",
  keywords: "Keywords",
  country: "Country",
  researcher_links: "Web pages",
  external_identifiers: "Other identifiers",
};

export const ITEM_LABELS: Record<RecordItems, string> = {
  affiliations: "Affiliations",
  works: "Works",
  fundings: "Funding",
};

function years(start?: number, end?: number): string {
  if (!start && !end) return "";
  return ` (${start ?? "?"}–${end ?? "present"})`;
}

/** What one section of a record says, in a line. */
export function sectionText(record: ResearcherRecord, section: RecordSection): string {
  switch (section) {
    case "researcher_name":
    case "biography":
      return record[section] ?? "";
    case "other_names":
    case "keywords":
    case "country":
      return (record[section] ?? []).join(", ");
    case "researcher_links":
      return (record.researcher_links ?? []).map((l) => l.link_title ?? l.link_url).join(", ");
    case "external_identifiers":
      return (record.external_identifiers ?? [])
        .map((i) => `${i.identifier_type} ${i.identifier_value}`)
        .join(", ");
  }
}

/** Each item of an itemised section, by put-code, in a line. */
export function itemsOf(record: ResearcherRecord, section: RecordItems): [string, string][] {
  if (section === "affiliations") {
    return (record.affiliations ?? []).map((a) => [
      a.put_code,
      `${a.role_title ? `${a.role_title}, ` : ""}${a.organisation_name}${years(a.start_year, a.end_year)}`,
    ]);
  }
  if (section === "works") {
    return (record.works ?? []).map((w) => [
      w.put_code,
      `${w.work_title}${w.publication_year ? ` (${w.publication_year})` : ""}`,
    ]);
  }
  return (record.fundings ?? []).map((f) => [
    f.put_code,
    `${f.funding_title}, ${f.funder_name}${years(f.start_year, f.end_year)}`,
  ]);
}

/** What `record` holds, as the choice that would keep it again. */
export function choiceOf(record: ResearcherRecord | undefined): KeepChoice {
  return {
    sections: record ? RECORD_SECTIONS.filter((s) => sectionText(record, s) !== "") : [],
    affiliations: (record?.affiliations ?? []).map((a) => a.put_code),
    works: (record?.works ?? []).map((w) => w.put_code),
    fundings: (record?.fundings ?? []).map((f) => f.put_code),
  };
}
