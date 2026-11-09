/**
 * A payload, laid out from its class's JSON Schema and the agent's derivations.
 *
 * A list of records is a table with one column per field. A field the specification says is
 * produced by a template, a model, keyword rules or a registry carries a badge saying so, read
 * from the record's own `recorded_in` field when there is one; that field is not shown as a
 * column. Each record's `grounded_on` becomes numbered links to the evidence it rests on, named
 * from the evidence; a citation with no matching evidence item is flagged. The top-level
 * `grounded_on` is the evidence list itself, so it is not repeated. A drafted document's text
 * (the contract's `Document`: `document_text` with its `media_type`) is shown as a document
 * (the provider's `Document` slot) rather than as one value among the facts.
 *
 * A class with a renderer registered under its name (`AgentViewProvider`'s `renderers`, or this
 * component's own) is drawn by that renderer instead. Nothing here names a class.
 */

import type { ComponentType } from "react";

import { isEmpty, makeContext, recorders } from "../../payload/context";
import { DOCUMENT_TEXT, documentOf } from "../../payload/document";
import type { EvidenceItem } from "../../payload/types";
import { type JsonSchema, properties, shapeOf } from "../../schema/shape";
import type { Derivation } from "../../spec/read";
import { type PayloadRendererProps, useAgentView } from "../Provider";
import { Facts } from "./Facts";
import { Section } from "./Section";

export function PayloadView({
  payload,
  schema,
  derivations = [],
  evidence = [],
  idPrefix,
  className,
  renderers,
}: {
  payload: Record<string, unknown>;
  schema: JsonSchema | undefined;
  derivations?: Derivation[];
  evidence?: EvidenceItem[];
  /** Prefixes every element id, so that two payloads on one page do not clash. */
  idPrefix: string;
  /** The payload's class name, for choosing a registered renderer. */
  className?: string | null | undefined;
  /** Renderers by class name, over the provider's. */
  renderers?: Record<string, ComponentType<PayloadRendererProps>>;
}) {
  const options = useAgentView();
  const { Document } = options.components;
  const ctx = schema ? makeContext(schema, derivations, evidence, idPrefix) : null;
  const Renderer = className ? (renderers?.[className] ?? options.renderers[className]) : undefined;
  if (Renderer && className) {
    return <Renderer payload={payload} className={className} schema={schema} ctx={ctx} />;
  }
  if (!schema || !ctx) {
    return (
      <>
        <p>There is no schema for this result, so it is shown as it arrived.</p>
        <pre className="json-view">{JSON.stringify(payload, null, 2)}</pre>
      </>
    );
  }
  const hidden = recorders(ctx, "");
  const document = documentOf(payload);
  if (document) hidden.add(DOCUMENT_TEXT);
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
      {document && <Document document={document} headingId={`${idPrefix}-document-heading`} />}
      {sections.map(([name, s]) => (
        <Section key={name} name={name} schema={s} value={payload[name]} ctx={ctx} />
      ))}
    </div>
  );
}
