import { useEffect, useState } from "react";

import { AgentDirectory } from "./components/capabilities/AgentDirectory";
import { Frame } from "./components/frame/Frame";
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
    <Frame
      {...(state.state === "loaded"
        ? {
            context: {
              actingFor: state.directory.actingFor,
              profileRef: state.directory.profileRef,
            },
          }
        : {})}
    >
      <h1>What Data Director can do here</h1>
      {state.state === "loading" && <p role="status">Loading the agents…</p>}
      {state.state === "failed" && (
        <div role="alert" className="callout status-danger">
          <p>Data Director could not list its agents: {state.message}.</p>
        </div>
      )}
      {state.state === "loaded" && <AgentDirectory directory={state.directory} />}
    </Frame>
  );
}
