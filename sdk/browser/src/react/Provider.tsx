/**
 * What a host page lends the components: how to render Markdown and a drafted document, a renderer
 * for any payload class that needs more than the schema-driven layout, and a view for any A2A
 * extension beyond the Data Director's own. Every slot has a plain default, so the components work
 * without a provider; the library itself depends on nothing but React.
 */

import { type ComponentType, createContext, type ReactNode, useContext, useMemo } from "react";

import type { AgentExtension } from "../card/types";
import type { Context } from "../payload/context";
import type { DocumentPart } from "../payload/document";
import type { JsonSchema } from "../schema/shape";
import { fieldName } from "../wording";

export interface DocumentProps {
  document: DocumentPart;
  headingId: string;
}

/** A payload class's own renderer, chosen by class name (the agent's `payload`). */
export interface PayloadRendererProps {
  payload: Record<string, unknown>;
  className: string;
  schema: JsonSchema | undefined;
  /** Null when there is no schema to lay the payload out from. */
  ctx: Context | null;
}

export interface ExtensionViewProps {
  extension: AgentExtension;
  idPrefix: string;
}

export interface Slots {
  Markdown: ComponentType<{ children: string }>;
  Document: ComponentType<DocumentProps>;
}

export interface AgentViewOptions {
  components: Slots;
  /** By payload class name. */
  renderers: Record<string, ComponentType<PayloadRendererProps>>;
  /** By extension URI; these take precedence over the built-in views. */
  extensions: Record<string, ComponentType<ExtensionViewProps>>;
}

/** Markdown shown as written, with its line breaks kept. */
function PlainMarkdown({ children }: { children: string }) {
  return <pre className="json-view">{children}</pre>;
}

/** A drafted document: its title, then its text, rendered when it is Markdown. */
function PlainDocument({ document, headingId }: DocumentProps) {
  const { Markdown } = useAgentView().components;
  const title = document.title ?? (document.kind ? fieldName(document.kind) : "Document");
  const markdown = document.mediaType.split(";")[0]?.trim().toLowerCase() === "text/markdown";
  return (
    <section className="document-result" aria-labelledby={headingId}>
      <h4 id={headingId}>{title}</h4>
      {markdown ? (
        <div className="markdown document-body">
          <Markdown>{document.text}</Markdown>
        </div>
      ) : (
        <pre className="json-view document-body">{document.text}</pre>
      )}
    </section>
  );
}

const DEFAULTS: AgentViewOptions = {
  components: { Markdown: PlainMarkdown, Document: PlainDocument },
  renderers: {},
  extensions: {},
};

const AgentViewContext = createContext<AgentViewOptions>(DEFAULTS);

export function useAgentView(): AgentViewOptions {
  return useContext(AgentViewContext);
}

/** Lends its children the given slots and registries, over whatever an outer provider lends. */
export function AgentViewProvider({
  components,
  renderers,
  extensions,
  children,
}: {
  components?: Partial<Slots>;
  renderers?: AgentViewOptions["renderers"];
  extensions?: AgentViewOptions["extensions"];
  children: ReactNode;
}) {
  const outer = useAgentView();
  const value = useMemo(
    () => ({
      components: { ...outer.components, ...components },
      renderers: { ...outer.renderers, ...renderers },
      extensions: { ...outer.extensions, ...extensions },
    }),
    [outer, components, renderers, extensions],
  );
  return <AgentViewContext.Provider value={value}>{children}</AgentViewContext.Provider>;
}
