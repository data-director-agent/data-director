/**
 * A result, laid out from its class's JSON Schema and the manifest's derivations: a simplified
 * port of the workbench viewer's `payloadUi` (workbench/viewer/js/payload.js).
 *
 * A list of records is a table with one column per field. A field the manifest says is produced
 * by a template, a model, keyword rules or a registry carries a badge saying so, read from the
 * record's own `recorded_in` field when there is one; that field is not shown as a column. Each
 * record's `grounded_on` becomes numbered links to the evidence it rests on, named from the
 * evidence; a citation with no matching evidence item is flagged. The top-level `grounded_on`
 * is the evidence list itself, so it is not repeated. A drafted document's text (the contract's
 * `Document`: `document_text` with its `media_type`) is shown as a document, rendered when it is
 * Markdown, rather than as one value among the facts. The parts are in `result/`.
 *
 * TODO(#70): the full renderer, with per-class renderers in a registry.
 */

import "./ResultView.css";

import type { Derivation } from "../../manifest/normalise";
import { type JsonSchema, properties, shapeOf } from "../../run/schema";
import type { EvidenceItem } from "../../run/types";
import { documentName } from "../../project/name";
import { isEmpty, makeContext, recorders } from "./result/context";
import { DocumentText } from "./result/DocumentText";
import { Facts } from "./result/Facts";
import { Section } from "./result/Section";

export function ResultView({
  payload,
  schema,
  derivations,
  evidence,
  idPrefix,
}: {
  payload: Record<string, unknown>;
  schema: JsonSchema | undefined;
  derivations: Derivation[];
  evidence: EvidenceItem[];
  idPrefix: string;
}) {
  if (!schema) {
    return (
      <>
        <p>This deployment has no schema for this result, so it is shown as it arrived.</p>
        <pre className="json-view">{JSON.stringify(payload, null, 2)}</pre>
      </>
    );
  }
  const ctx = makeContext(schema, derivations, evidence, idPrefix);
  const hidden = recorders(ctx, "");
  const document = documentOf(payload);
  if (document) hidden.add(TEXT);
  const sections = properties(schema).filter(
    ([name]) => name !== "grounded_on" && !hidden.has(name) && !isEmpty(payload[name]),
  );
  const scalars = sections.filter(([, s]) => {
    const kind = shapeOf(schema, s).kind;
    return kind === "scalar" || kind === "list";
  });
  return (
    <div className="result">
      {scalars.length > 0 && (
        <Facts
          schema={{ properties: Object.fromEntries(scalars) }}
          value={payload}
          path=""
          ctx={ctx}
        />
      )}
      {document && (
        <DocumentText
          text={document.text}
          mediaType={document.mediaType}
          title={document.title}
          headingId={`${idPrefix}-document-heading`}
        />
      )}
      {sections.map(([name, s]) => (
        <Section key={name} name={name} schema={s} value={payload[name]} ctx={ctx} />
      ))}
    </div>
  );
}

const TEXT = "document_text";
/** The document a payload carries, when it is the contract's `Document`. */
function documentOf(
  payload: Record<string, unknown>,
): { text: string; mediaType: string; title: string } | null {
  const text = payload[TEXT];
  const mediaType = payload.media_type;
  if (typeof text !== "string" || typeof mediaType !== "string") return null;
  const title = payload.document_title;
  const kind = payload.document_kind;
  return {
    text,
    mediaType,
    title: documentName({
      document_title: typeof title === "string" && title ? title : null,
      document_kind: typeof kind === "string" ? kind : "other",
    }),
  };
}
