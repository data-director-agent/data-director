import { useEffect, useState } from "react";

import { AgentDirectory } from "./components/capabilities/AgentDirectory";
import { ConversationHome } from "./components/conversation/ConversationHome";
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
  const [view, setView] = useState<"conversation" | "directory">("conversation");

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
      {state.state === "loading" && <p role="status">Loading the agents…</p>}
      {state.state === "failed" && (
        <div role="alert" className="callout status-danger">
          <p>Data Director could not list its agents: {state.message}.</p>
        </div>
      )}
      {state.state === "loaded" && view === "conversation" && (
        <ConversationHome
          directory={state.directory}
          onOpenDirectory={() => setView("directory")}
        />
      )}
      {state.state === "loaded" && view === "directory" && (
        <>
          <p>
            <button type="button" onClick={() => setView("conversation")}>
              Back to the conversation
            </button>
          </p>
          <h1>What Data Director can do here</h1>
          <AgentDirectory directory={state.directory} />
        </>
      )}
    </Frame>
  );
}
