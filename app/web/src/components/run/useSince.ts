/**
 * How long, in milliseconds, since `key` last changed, counted on this device and redrawn each
 * second while `ticking`. The run view uses it for a stage's elapsed time and for how long the
 * stream has been quiet; the stream carries no times of its own, so this is when the page saw it.
 */

import { useEffect, useState } from "react";

const TICK_MS = 1000;

export function useSince(key: unknown, ticking: boolean): number {
  const [counted, setCounted] = useState({ key, ms: 0 });
  // A new key restarts the count: set during render, so the stale count is never drawn.
  if (!Object.is(counted.key, key)) setCounted({ key, ms: 0 });
  useEffect(() => {
    if (!ticking) return undefined;
    const from = Date.now();
    const id = setInterval(() => setCounted({ key, ms: Date.now() - from }), TICK_MS);
    return () => clearInterval(id);
  }, [key, ticking]);
  return Object.is(counted.key, key) ? counted.ms : 0;
}

/** `ms` as minutes and seconds, `m:ss`. */
export function formatElapsed(ms: number): string {
  const seconds = Math.floor(ms / 1000);
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}
