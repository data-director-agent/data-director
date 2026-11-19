/**
 * The lines one version of a document changed from the one before, so that a person can see
 * what a revision did: each line of either text is kept, added or removed, in reading order.
 *
 * The diff is a longest common subsequence of lines, which needs no dependency and is exact for
 * the documents agents draft, a few hundred lines at most. Past `MAX_CELLS` comparisons it gives
 * up on alignment and shows the old text removed and the new text added, rather than hold the
 * page while it compares.
 */

export type LineChange = { kind: "kept" | "added" | "removed"; text: string };

/** The largest lines-times-lines table compared: about 2,000 lines on each side. */
export const MAX_CELLS = 4_000_000;

function lines(text: string): string[] {
  if (text === "") return [];
  return text.replace(/\r\n/g, "\n").replace(/\n$/, "").split("\n");
}

export function diffLines(before: string, after: string): LineChange[] {
  const a = lines(before);
  const b = lines(after);
  if (a.length * b.length > MAX_CELLS) {
    return [
      ...a.map((text) => ({ kind: "removed" as const, text })),
      ...b.map((text) => ({ kind: "added" as const, text })),
    ];
  }
  // common[i][j]: the length of the longest common subsequence of a[i..] and b[j..].
  const width = b.length + 1;
  const common = new Uint32Array((a.length + 1) * width);
  for (let i = a.length - 1; i >= 0; i--) {
    for (let j = b.length - 1; j >= 0; j--) {
      common[i * width + j] =
        a[i] === b[j]
          ? (common[(i + 1) * width + j + 1] ?? 0) + 1
          : Math.max(common[(i + 1) * width + j] ?? 0, common[i * width + j + 1] ?? 0);
    }
  }
  const changes: LineChange[] = [];
  let i = 0;
  let j = 0;
  while (i < a.length && j < b.length) {
    const left = a[i] as string;
    const right = b[j] as string;
    if (left === right) {
      changes.push({ kind: "kept", text: left });
      i++;
      j++;
    } else if ((common[(i + 1) * width + j] ?? 0) >= (common[i * width + j + 1] ?? 0)) {
      changes.push({ kind: "removed", text: left });
      i++;
    } else {
      changes.push({ kind: "added", text: right });
      j++;
    }
  }
  for (; i < a.length; i++) changes.push({ kind: "removed", text: a[i] as string });
  for (; j < b.length; j++) changes.push({ kind: "added", text: b[j] as string });
  return changes;
}
