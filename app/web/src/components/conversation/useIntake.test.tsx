import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";

import completeFixture from "../../../fixtures/intake-complete.json";
import pendingFixture from "../../../fixtures/intake-pending.json";
import { type ProjectApi, ProjectApiContext, type ProjectIntake } from "../../project/api";
import { type IntakeEvents, useIntake } from "./useIntake";

const PENDING = pendingFixture as ProjectIntake;
const COMPLETE = completeFixture as ProjectIntake;

function render(overrides: Partial<ProjectApi>, projectId: string | null = "p1") {
  const api = {
    intake: () => Promise.resolve(PENDING),
    answerIntake: () => Promise.resolve(COMPLETE),
    dismissIntake: () => Promise.resolve(COMPLETE),
    ...overrides,
  } as unknown as ProjectApi;
  const events: IntakeEvents = { progressed: vi.fn(), announce: vi.fn(), failed: vi.fn() };
  const wrapper = ({ children }: { children: ReactNode }) => (
    <ProjectApiContext.Provider value={api}>{children}</ProjectApiContext.Provider>
  );
  const view = renderHook(
    ({ id, turnCount }: { id: string | null; turnCount: number }) => useIntake(id, turnCount, events),
    { wrapper, initialProps: { id: projectId, turnCount: 0 } },
  );
  return { ...view, events };
}

describe("useIntake", () => {
  it("opens the card while the intake is first read pending", async () => {
    const { result } = render({});
    await waitFor(() => expect(result.current.intake?.open).toBe(true));
    expect(result.current.intake?.again).toBe(false);
  });

  it("leaves the card closed for a completed intake", async () => {
    const { result } = render({ intake: () => Promise.resolve(COMPLETE) });
    await waitFor(() => expect(result.current.intake).not.toBeNull());
    expect(result.current.intake?.open).toBe(false);
  });

  it("changes what the card holds after a turn, never whether it is open", async () => {
    const intake = vi
      .fn<ProjectApi["intake"]>()
      .mockResolvedValueOnce(PENDING)
      .mockResolvedValue(COMPLETE);
    const { result, rerender } = render({ intake });
    await waitFor(() => expect(result.current.intake?.open).toBe(true));
    act(() => result.current.close());
    rerender({ id: "p1", turnCount: 1 });
    await waitFor(() => expect(result.current.intake?.intake).toEqual(COMPLETE));
    expect(result.current.intake?.open).toBe(false);
  });

  it("opens the card again with the intake read afresh", async () => {
    const intake = vi
      .fn<ProjectApi["intake"]>()
      .mockResolvedValueOnce(COMPLETE)
      .mockResolvedValue(PENDING);
    const { result } = render({ intake });
    await waitFor(() => expect(result.current.intake).not.toBeNull());
    act(() => result.current.openAgain("p1"));
    await waitFor(() => expect(result.current.intake?.again).toBe(true));
    expect(result.current.intake).toMatchObject({ open: true, intake: PENDING });
  });

  it("holds an answer's intake and passes on the progress it returned", async () => {
    const { result, events } = render({});
    await waitFor(() => expect(result.current.intake).not.toBeNull());
    await act(() => result.current.answer("p1", "q", ["1"]));
    expect(result.current.intake?.intake).toEqual(COMPLETE);
    expect(events.progressed).toHaveBeenCalledWith("p1", COMPLETE.progress);
  });

  it("closes the card and says so when the questions are skipped", async () => {
    const { result, events } = render({});
    await waitFor(() => expect(result.current.intake?.open).toBe(true));
    act(() => result.current.dismiss("p1"));
    await waitFor(() => expect(result.current.intake?.open).toBe(false));
    expect(events.announce).toHaveBeenCalledTimes(1);
  });

  it("says when the questions could not be skipped", async () => {
    const { result, events } = render({ dismissIntake: () => Promise.reject(new Error("down")) });
    await waitFor(() => expect(result.current.intake?.open).toBe(true));
    act(() => result.current.dismiss("p1"));
    await waitFor(() => expect(events.failed).toHaveBeenCalledTimes(1));
    expect(result.current.intake?.open).toBe(true);
  });

  it("has no intake without a project", () => {
    const intake = vi.fn<ProjectApi["intake"]>();
    const { result } = render({ intake }, null);
    expect(result.current.intake).toBeNull();
    expect(intake).not.toHaveBeenCalled();
  });
});
