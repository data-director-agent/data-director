/**
 * The contract's `Document`, recognised by its slots rather than its class name: a payload with
 * `document_text` and its `media_type` is a drafted document, shown as a document rather than as
 * one value among the facts.
 */

export const DOCUMENT_TEXT = "document_text";

export interface DocumentPart {
  text: string;
  mediaType: string;
  /** `document_kind`, such as `readme`; null when the payload does not say. */
  kind: string | null;
  /** `document_title`; null when the payload gives none. */
  title: string | null;
}

export function documentOf(payload: Record<string, unknown>): DocumentPart | null {
  const text = payload[DOCUMENT_TEXT];
  const mediaType = payload.media_type;
  if (typeof text !== "string" || typeof mediaType !== "string") return null;
  const title = payload.document_title;
  const kind = payload.document_kind;
  return {
    text,
    mediaType,
    kind: typeof kind === "string" ? kind : null,
    title: typeof title === "string" && title ? title : null,
  };
}
