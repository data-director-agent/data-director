/**
 * A run's result, laid out by `@data-director/agent-view`'s `PayloadView` from its class's JSON
 * Schema and the manifest's derivations (see that component for how). The shell lends it its own
 * Markdown renderer and its document view (`result/DocumentText`: copy and download), so that a
 * drafted document reads the same here as on the project's documents page.
 */

import "@data-director/agent-view/styles.css";

import type { Derivation, DocumentPart, EvidenceItem, JsonSchema } from "@data-director/agent-view";
import { AgentViewProvider, type DocumentProps, PayloadView, type Slots } from "@data-director/agent-view/react";

import { documentName } from "../../project/name";
import { Markdown } from "../ui/Markdown";
import { DocumentText } from "./result/DocumentText";

/** What the shell calls a document: its title, or the name of its kind. */
function title(document: DocumentPart): string {
  return documentName({ document_title: document.title, document_kind: document.kind ?? "other" });
}

function ShellDocument({ document, headingId }: DocumentProps) {
  return (
    <DocumentText
      text={document.text}
      mediaType={document.mediaType}
      title={title(document)}
      headingId={headingId}
    />
  );
}

const SLOTS: Slots = { Markdown, Document: ShellDocument };

export function ResultView({
  payload,
  schema,
  className,
  derivations,
  evidence,
  idPrefix,
}: {
  payload: Record<string, unknown>;
  schema: JsonSchema | undefined;
  /** The payload's class name, for a renderer registered for it. */
  className?: string | null;
  derivations: Derivation[];
  evidence: EvidenceItem[];
  idPrefix: string;
}) {
  return (
    <AgentViewProvider components={SLOTS}>
      <PayloadView
        payload={payload}
        schema={schema}
        className={className}
        derivations={derivations}
        evidence={evidence}
        idPrefix={idPrefix}
      />
    </AgentViewProvider>
  );
}
