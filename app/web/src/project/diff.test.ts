import { MAX_CELLS, diffLines } from "./diff";

describe("diffLines", () => {
  it("keeps the lines both texts share and marks the rest", () => {
    expect(diffLines("# Untitled\n\nCores.\n", "# Soil cores\n\nCores.\nSite: north.\n")).toEqual([
      { kind: "removed", text: "# Untitled" },
      { kind: "added", text: "# Soil cores" },
      { kind: "kept", text: "" },
      { kind: "kept", text: "Cores." },
      { kind: "added", text: "Site: north." },
    ]);
  });

  it("finds nothing changed in the same text, whatever its line endings", () => {
    const changes = diffLines("a\r\nb\r\n", "a\nb\n");
    expect(changes.every((change) => change.kind === "kept")).toBe(true);
  });

  it("treats empty text as no lines", () => {
    expect(diffLines("", "a\n")).toEqual([{ kind: "added", text: "a" }]);
    expect(diffLines("a\n", "")).toEqual([{ kind: "removed", text: "a" }]);
  });

  it("shows all removed then all added past the comparison limit", () => {
    const side = Math.ceil(Math.sqrt(MAX_CELLS)) + 1;
    const before = Array.from({ length: side }, (_, i) => `a${i}`).join("\n");
    const after = Array.from({ length: side }, (_, i) => `b${i}`).join("\n");
    const changes = diffLines(before, after);
    expect(changes).toHaveLength(2 * side);
    expect(changes[0]?.kind).toBe("removed");
    expect(changes[side]?.kind).toBe("added");
  });
});
