/** How a citation (`GroundingRef`) finds the evidence item it names, and where that item is shown. */

/** An evidence item and a citation match on both the source id and the content hash. */
export function evidenceKey(item: { source_id: string; content_hash?: string | null }): string {
  return `${item.source_id}|${item.content_hash ?? ""}`;
}

/** The element id a page gives evidence item `index` (from 0), for a citation to link to. */
export function evidenceAnchor(idPrefix: string, index: number): string {
  return `${idPrefix}-evidence-${index + 1}`;
}

/** The credit a source's licence asks for beside a record from it: the words to show and the
 * licence they link to. Sources are told apart by the label of the copy that answered
 * (`snapshot_ref`), not by any agent. */
export interface EvidenceCredit {
  text: string;
  href: string;
}

const CREDITS: readonly { prefix: string; credit: EvidenceCredit }[] = [
  {
    prefix: "open-policy-finder:",
    credit: {
      text: "Jisc Open Policy Finder, CC BY-NC-ND 4.0 (non-commercial use)",
      href: "https://creativecommons.org/licenses/by-nc-nd/4.0/",
    },
  },
];

/** The credit due for an evidence item, or null when its source asks for none. */
export function evidenceCredit(item: { snapshot_ref?: string | null }): EvidenceCredit | null {
  const ref = item.snapshot_ref ?? "";
  return CREDITS.find((c) => ref.startsWith(c.prefix))?.credit ?? null;
}
