import { useEffect, useState } from "react";

import { AgentDirectory } from "./components/capabilities/AgentDirectory";
import { ConversationHome } from "./components/conversation/ConversationHome";
import { Frame } from "./components/frame/Frame";
import { PageHeader } from "./components/frame/PageHeader";
import { useLocation } from "./route";
import { type Directory, normalise } from "./manifest/normalise";
import type { RawAgentsResponse } from "./manifest/types";

type Load =
  | { state: "loading" }
  | { state: "failed"; message: string }
  | { state: "loaded"; directory: Directory };

export async function fetchDirectory(signal?: AbortSignal): Promise<Directory> {
  const response = await fetch("/api/agents", signal ? { signal } : {});
  if (!response.ok) throw new Error(`the server answered ${response.status}`);
  return normalise((await response.json()) as RawAgentsResponse);
}

export function App({ load = fetchDirectory }: { load?: typeof fetchDirectory }) {
  const [state, setState] = useState<Load>({ state: "loading" });
  const location = useLocation();
  const [path = "/", query] = location.split("?");
  const onAgents = path === "/agents";

  useEffect(() => {
    const controller = new AbortController();
    load(controller.signal).then(
      (directory) => setState({ state: "loaded", directory }),
      (error: unknown) => {
        if (controller.signal.aborted) return;
        setState({ state: "failed", message: error instanceof Error ? error.message : String(error) });
      },
    );
    return () => controller.abort();
  }, [load]);

  return (
    <Frame current={onAgents ? "/agents" : "/"}>
      {state.state === "loading" && <p role="status">Loading the agents…</p>}
      {state.state === "failed" && (
        <div role="alert" className="callout status-danger">
          <p>Data Director could not list its agents: {state.message}.</p>
        </div>
      )}
      {state.state === "loaded" && !onAgents && <ConversationHome directory={state.directory} />}
      {state.state === "loaded" && onAgents && (
        <>
          <PageHeader title="Agents: what Data Director can do here">
            <ActingFor directory={state.directory} />
          </PageHeader>
          <AgentDirectory
            directory={state.directory}
            initial={new URLSearchParams(query).get("agent") ?? undefined}
          />
        </>
      )}
    </Frame>
  );
}

/**
 * Whom runs act for and whose rules apply. Until there is authentication (ADR-0018, #17) the
 * principal is the operator's assertion, and the line says so. On the conversation the
 * workspace's status bar says this.
 */
function ActingFor({ directory: { actingFor, profileRef } }: { directory: Directory }) {
  return (
    <p className="hint">
      Acting as {actingFor.name} (
      {actingFor.assurance === "asserted"
        ? "asserted by the operator, not authenticated"
        : actingFor.assurance}
      ) · Policy <code>{profileRef}</code>
    </p>
  );
}
