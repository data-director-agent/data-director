import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { useResource } from "./useResource";

/** A read that lands only when told to, recording the signal it was given. */
function deferred<T>() {
  const reads: { key: string; signal: AbortSignal; resolve(v: T): void; reject(e: unknown): void }[] =
    [];
  const load = vi.fn(
    (key: string, signal: AbortSignal) =>
      new Promise<T>((resolve, reject) => reads.push({ key, signal, resolve, reject })),
  );
  return { load, reads };
}

describe("useResource", () => {
  it("is loading until the read lands, then holds its value", async () => {
    const { result } = renderHook(() => useResource("p1", () => Promise.resolve(42)));
    expect(result.current.resource.state).toBe("loading");
    await waitFor(() => expect(result.current.resource).toEqual({ state: "loaded", value: 42 }));
    expect(result.current.latest).toBe(42);
  });

  it("says why a read failed", async () => {
    const { result } = renderHook(() =>
      useResource("p1", () => Promise.reject(new Error("down"))),
    );
    await waitFor(() => expect(result.current.resource.state).toBe("failed"));
    expect(result.current.latest).toBeUndefined();
  });

  it("reads nothing without a key", () => {
    const load = vi.fn(() => Promise.resolve(1));
    const { result } = renderHook(() => useResource(null, load));
    expect(load).not.toHaveBeenCalled();
    expect(result.current.resource.state).toBe("loading");
  });

  it("aborts the read of the previous key and never shows it as the new key's", async () => {
    const { load, reads } = deferred<string>();
    const { result, rerender } = renderHook(({ key }) => useResource(key, load), {
      initialProps: { key: "p1" },
    });
    rerender({ key: "p2" });
    const [first, second] = reads;
    expect(first?.signal.aborted).toBe(true);
    act(() => first?.resolve("of p1"));
    expect(result.current.resource.state).toBe("loading");
    act(() => second?.resolve("of p2"));
    await waitFor(() =>
      expect(result.current.resource).toEqual({ state: "loaded", value: "of p2" }),
    );
  });

  it("shows a held value only for the key it was read for", async () => {
    const { result, rerender } = renderHook(
      ({ key }) => useResource(key, (k) => (k === "p1" ? Promise.resolve(1) : new Promise(() => {}))),
      { initialProps: { key: "p1" } },
    );
    await waitFor(() => expect(result.current.resource.state).toBe("loaded"));
    rerender({ key: "p2" });
    expect(result.current.resource.state).toBe("loading");
    expect(result.current.latest).toBeUndefined();
  });

  it("reads again when refresh changes, keeping the value meanwhile", async () => {
    let n = 0;
    const load = vi.fn(() => Promise.resolve(++n));
    const { result, rerender } = renderHook(({ refresh }) => useResource("p1", load, refresh), {
      initialProps: { refresh: 0 },
    });
    await waitFor(() => expect(result.current.latest).toBe(1));
    rerender({ refresh: 1 });
    expect(result.current.latest).toBe(1);
    await waitFor(() => expect(result.current.latest).toBe(2));
    expect(load).toHaveBeenCalledTimes(2);
  });

  it("keeps the latest value when a later read of the same key fails", async () => {
    const load = vi
      .fn<() => Promise<number>>()
      .mockResolvedValueOnce(1)
      .mockRejectedValueOnce(new Error("down"));
    const { result } = renderHook(() => useResource("p1", load));
    await waitFor(() => expect(result.current.latest).toBe(1));
    act(() => result.current.reload());
    await waitFor(() => expect(result.current.resource.state).toBe("failed"));
    expect(result.current.latest).toBe(1);
  });

  it("holds a value set by the page for the current key, and drops one for another", () => {
    const { result } = renderHook(() => useResource("p1", () => new Promise<number>(() => {})));
    act(() => result.current.set("p1", 7));
    expect(result.current.resource).toEqual({ state: "loaded", value: 7 });
    act(() => result.current.set("p2", 8));
    expect(result.current.resource).toEqual({ state: "loaded", value: 7 });
  });

  it("tells the caller as each read lands", async () => {
    const loaded = vi.fn();
    const failed = vi.fn();
    const load = vi
      .fn<() => Promise<number>>()
      .mockResolvedValueOnce(1)
      .mockRejectedValueOnce(new Error("down"));
    const { result } = renderHook(() => useResource("p1", load, undefined, { loaded, failed }));
    await waitFor(() => expect(loaded).toHaveBeenCalledWith(1, "p1"));
    act(() => result.current.reload());
    await waitFor(() => expect(failed).toHaveBeenCalledWith("down", "p1"));
  });

  it("aborts its read when the component goes", () => {
    const { load, reads } = deferred<number>();
    const { unmount } = renderHook(() => useResource("p1", load));
    unmount();
    expect(reads[0]?.signal.aborted).toBe(true);
  });
});
