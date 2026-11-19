/**
 * The personal-data findings an inventory carries, in words a researcher reads
 * (docs/specs/personal-data.md, Wording for researchers). A finding says where the inventory
 * command found what may be personal data, never what: so does everything said here. Nothing
 * here may read a clean result as safe.
 */

import type { FileInventory, PersonalDataFinding, PersonalDataKind } from "./types";

/** Whether the inventory was checked for personal data and, if so, whether anything was found. */
export type PersonalDataState = "not checked" | "nothing found" | "found";

export function personalDataState(inventory: FileInventory): PersonalDataState {
  const findings = inventory.inventory_personal_data;
  if (findings === undefined) return "not checked";
  return findings.length ? "found" : "nothing found";
}

/** What is said for each state, in the substance the spec gives. */
export const PERSONAL_DATA_TEXT: Readonly<Record<PersonalDataState, string>> = {
  found:
    "Possible personal data was found in these places. The inventory does not include the " +
    "values. Check them before you add the inventory, and talk to your data steward or ethics " +
    "contact about how they should be handled. Data Director does not change your files.",
  "nothing found":
    "No direct identifiers were found in the rows and names that were checked. This does not " +
    "mean the data hold no personal data: free text beyond the files checked, other formats, " +
    "indirect identifiers and rows beyond the sample were not checked.",
  "not checked":
    "This inventory was made without a check for personal data, so it says nothing about " +
    "whether the data hold any. The inventory command checks on your computer unless it is told " +
    "not to.",
};

/** The findings of `inventory` by place, in the order they are listed: a folder's under its path
 * and a trailing slash. */
export function findingsByPlace(inventory: FileInventory): Map<string, PersonalDataFinding[]> {
  const byPlace = new Map<string, PersonalDataFinding[]>();
  for (const f of inventory.inventory_personal_data ?? []) {
    byPlace.set(f.finding_file, [...(byPlace.get(f.finding_file) ?? []), f]);
  }
  return byPlace;
}

const KIND_LABELS: Readonly<Record<PersonalDataKind, string>> = {
  "email address": "E-mail addresses",
  "phone number": "Telephone numbers",
  "NHS number": "NHS numbers",
  "National Insurance number": "National Insurance numbers",
  postcode: "Postcodes",
  "passport number": "Passport numbers",
  "driving licence number": "Driving licence numbers",
  "bank account number": "Bank account numbers",
  "payment card number": "Payment card numbers",
  "IP address": "IP addresses",
  "person name": "Names of people",
  "direct identifier": "a direct identifier, such as a name or contact details",
  "indirect identifier": "an indirect identifier, such as an age or a date of birth",
  "special category": "special category data, such as health",
  location: "a precise location",
};

const SHARES: Readonly<Record<NonNullable<PersonalDataFinding["finding_proportion"]>, string>> = {
  "under 1%": "in under 1% of the sampled values",
  "1 to 10%": "in 1 to 10% of the sampled values",
  "10 to 50%": "in 10 to 50% of the sampled values",
  "over 50%": "in over half the sampled values",
};

/** One finding in words: what may be there, where in the file, and how much of it. */
export function findingLabel(finding: PersonalDataFinding): string {
  const kind = KIND_LABELS[finding.finding_kind];
  const column = finding.finding_column;
  switch (finding.finding_target) {
    case "field name":
      return `The column name ${column ?? ""} suggests ${kind}`;
    case "file name":
      return `The name suggests ${kind}`;
    case "text":
      return `${kind} in the text`;
    case "column": {
      const share = finding.finding_proportion ? `, ${SHARES[finding.finding_proportion]}` : "";
      return `${kind} in the column ${column ?? ""}${share}`;
    }
  }
}

/** How sure the check is, in words. */
export function confidenceLabel(finding: PersonalDataFinding): string {
  return `${finding.finding_confidence} confidence`;
}
