import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";

import intakeFixture from "../../../fixtures/intake-pending.json";
import type { ProjectProgress } from "../../flow/types";
import { type ProjectApi, ProjectApiContext, type ProjectIntake } from "../../project/api";
import { useProjectProgress } from "./useProjectProgress";

const PROGRESS = (intakeFixture as ProjectIntake).progress;
const CHANGED: ProjectProgress = { ...PROGRESS, entry_point: 3 } as ProjectProgress;

function render(progress: ProjectApi["progress"], projectId: string | null = "p1") {
  const api = { progress } as unknown as ProjectApi;
  const wrapper = ({ children }: { children: ReactNode }) => (
    <ProjectApiContext.Provider value={api}>{children}</ProjectApiContext.Provider>
  );
  return renderHook(
    ({ id, turnCount }: { id: string | null; turnCount: number }) => useProjectProgress(id, turnCount),
    { wrapper, initialProps: { id: projectId, turnCount: 0 } },
  );
}

describe("useProjectProgress", () => {
  it("reads the project's progress, and again after each turn", async () => {
    const progress = vi.fn<ProjectApi["progress"]>(() => Promise.resolve(PROGRESS));
    const { result, rerender } = render(progress);
    await waitFor(() => expect(result.current.progress).toEqual(PROGRESS));
    rerender({ id: "p1", turnCount: 1 });
    await waitFor(() => expect(progress).toHaveBeenCalledTimes(2));
  });

  it("has no progress without a project", () => {
    const progress = vi.fn<ProjectApi["progress"]>();
    const { result } = render(progress, null);
    expect(result.current.progress).toBeUndefined();
    expect(progress).not.toHaveBeenCalled();
  });

  it("keeps the last progress when a read after a turn fails", async () => {
    const progress = vi
      .fn<ProjectApi["progress"]>()
      .mockResolvedValueOnce(PROGRESS)
      .mockRejectedValueOnce(new Error("down"));
    const { result, rerender } = render(progress);
    await waitFor(() => expect(result.current.progress).toEqual(PROGRESS));
    rerender({ id: "p1", turnCount: 1 });
    await waitFor(() => expect(progress).toHaveBeenCalledTimes(2));
    expect(result.current.progress).toEqual(PROGRESS);
  });

  it("holds what a change returns, or says why it failed", async () => {
    const { result } = render(() => Promise.resolve(PROGRESS));
    await waitFor(() => expect(result.current.progress).toEqual(PROGRESS));
    act(() => result.current.change(Promise.reject(new Error("refused")), "p1"));
    await waitFor(() => expect(result.current.error).toBe("refused"));
    act(() => result.current.change(Promise.resolve(CHANGED), "p1"));
    await waitFor(() => expect(result.current.progress).toEqual(CHANGED));
    expect(result.current.error).toBeNull();
  });
});
