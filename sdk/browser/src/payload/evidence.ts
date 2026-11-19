/** How a citation (`GroundingRef`) finds the evidence item it names, and where that item is shown. */

/** An evidence item and a citation match on both the source id and the content hash. */
export function evidenceKey(item: { source_id: string; content_hash?: string | null }): string {
  return `${item.source_id}|${item.content_hash ?? ""}`;
}

/** The element id a page gives evidence item `index` (from 0), for a citation to link to. */
export function evidenceAnchor(idPrefix: string, index: number): string {
  return `${idPrefix}-evidence-${index + 1}`;
}
