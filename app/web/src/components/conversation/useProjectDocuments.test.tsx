import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";

import projectFixture from "../../../fixtures/project-documents.json";
import { type ProjectApi, ProjectApiContext, type ProjectDocuments } from "../../project/api";
import { useProjectDocuments, type AwaitedDrafts } from "./useProjectDocuments";

const PROJECT = projectFixture as ProjectDocuments;
const DRAFTER = PROJECT.documents[0]?.versions[0]?.drafted_by?.invocation_id ?? "";

function render(documents: ProjectApi["documents"], initial: Props) {
  const api = { documents } as unknown as ProjectApi;
  const wrapper = ({ children }: { children: ReactNode }) => (
    <ProjectApiContext.Provider value={api}>{children}</ProjectApiContext.Provider>
  );
  const announce = vi.fn<(said: string) => void>();
  const view = renderHook(
    ({ projectId, turnCount, awaited }: Props) =>
      useProjectDocuments(projectId, turnCount, awaited, announce),
    { wrapper, initialProps: initial },
  );
  return { ...view, announce };
}

interface Props {
  projectId: string | null;
  turnCount: number;
  awaited: AwaitedDrafts | null;
}

describe("useProjectDocuments", () => {
  it("reads the project's documents, and again after each turn", async () => {
    const documents = vi.fn<ProjectApi["documents"]>(() => Promise.resolve(PROJECT));
    const { result, rerender } = render(documents, { projectId: "p1", turnCount: 0, awaited: null });
    await waitFor(() => expect(result.current.documents.state).toBe("loaded"));
    rerender({ projectId: "p1", turnCount: 1, awaited: null });
    await waitFor(() => expect(documents).toHaveBeenCalledTimes(2));
    expect(documents).toHaveBeenCalledWith("p1", expect.any(AbortSignal));
  });

  it("never shows another project's documents", async () => {
    const documents = vi.fn<ProjectApi["documents"]>((id) =>
      id === "p1" ? Promise.resolve(PROJECT) : new Promise(() => {}),
    );
    const { result, rerender } = render(documents, { projectId: "p1", turnCount: 0, awaited: null });
    await waitFor(() => expect(result.current.documents.state).toBe("loaded"));
    rerender({ projectId: "p2", turnCount: 0, awaited: null });
    expect(result.current.documents.state).toBe("loading");
  });

  it("says why the documents could not be read", async () => {
    const { result } = render(() => Promise.reject(new Error("down")), {
      projectId: "p1",
      turnCount: 0,
      awaited: null,
    });
    await waitFor(() => expect(result.current.documents).toEqual({ state: "failed", message: "down" }));
  });

  it("announces the reply again with what its runs drafted, once", async () => {
    const documents = vi.fn<ProjectApi["documents"]>(() => Promise.resolve(PROJECT));
    const awaited = { said: "New reply.", invocationIds: [DRAFTER] };
    const { announce, rerender } = render(documents, { projectId: "p1", turnCount: 1, awaited });
    await waitFor(() => expect(announce).toHaveBeenCalledTimes(1));
    expect(announce.mock.calls[0]?.[0]).toMatch(/^New reply\. .+ drafted, version 1/);
    rerender({ projectId: "p1", turnCount: 2, awaited });
    await waitFor(() => expect(documents).toHaveBeenCalledTimes(2));
    expect(announce).toHaveBeenCalledTimes(1);
  });

  it("announces nothing more when the turn's runs drafted nothing", async () => {
    const awaited = { said: "New reply.", invocationIds: ["another run"] };
    const { result, announce } = render(() => Promise.resolve(PROJECT), {
      projectId: "p1",
      turnCount: 1,
      awaited,
    });
    await waitFor(() => expect(result.current.documents.state).toBe("loaded"));
    expect(announce).not.toHaveBeenCalled();
  });

  it("holds the documents an answered question returned", async () => {
    const { result } = render(() => new Promise(() => {}), {
      projectId: "p1",
      turnCount: 0,
      awaited: null,
    });
    act(() => result.current.answered("p1", PROJECT));
    await waitFor(() => expect(result.current.documents.state).toBe("loaded"));
  });
});
