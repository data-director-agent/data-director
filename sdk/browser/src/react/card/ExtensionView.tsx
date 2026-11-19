/**
 * One A2A extension: its URI, whether it is required and its description, then its params. The
 * Data Director's own extensions are drawn field by field; a host may register a view for any
 * other URI (`AgentViewProvider`'s `extensions`); anything else is shown as key–value pairs.
 */

import type { ComponentType } from "react";

import { AGENT_SPEC_URI, MANIFEST_URI } from "../../card/extensions";
import type { AgentExtension } from "../../card/types";
import { readAgentSpec } from "../../spec/read";
import { type ExtensionViewProps, useAgentView } from "../Provider";
import { AgentSpecView } from "./AgentSpecView";
import { ManifestView } from "./ManifestView";
import { JsonValue, UrlLink } from "./parts";

function AgentSpecExtension({ extension }: ExtensionViewProps) {
  const spec = readAgentSpec(extension.params);
  return spec ? (
    <AgentSpecView spec={spec} />
  ) : (
    <>
      <p className="dd-issue">These params are not a readable agent specification.</p>
      <JsonValue value={extension.params} />
    </>
  );
}

function ManifestExtension({ extension, idPrefix }: ExtensionViewProps) {
  const agents = Array.isArray(extension.params?.agents) ? extension.params.agents : [];
  return <ManifestView agents={agents} idPrefix={idPrefix} />;
}

export const BUILT_IN_EXTENSIONS: Record<string, ComponentType<ExtensionViewProps>> = {
  [AGENT_SPEC_URI]: AgentSpecExtension,
  [MANIFEST_URI]: ManifestExtension,
};

export function ExtensionView({ extension, idPrefix }: { extension: AgentExtension; idPrefix: string }) {
  const registered = useAgentView().extensions;
  const View = registered[extension.uri] ?? BUILT_IN_EXTENSIONS[extension.uri];
  const params = extension.params;
  return (
    <div className="dd-extension">
      <p className="dd-item-head">
        <UrlLink url={extension.uri} />{" "}
        <span className="dd-chip">{extension.required ? "required" : "optional"}</span>
      </p>
      {extension.description && <p className="dd-muted">{extension.description}</p>}
      {View ? (
        <View extension={extension} idPrefix={idPrefix} />
      ) : (
        params && Object.keys(params).length > 0 && <JsonValue value={params} />
      )}
    </div>
  );
}
