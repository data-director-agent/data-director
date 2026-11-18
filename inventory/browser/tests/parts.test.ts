import { describe, expect, it } from "vitest";

import {
  applyEdits,
  asInventory,
  asParts,
  carryOver,
  diffInventories,
  edit,
  NO_EDITS,
  NotAnInventory,
  NotAPartFolder,
  omit,
  partFolderProblem,
  partOf,
  partProblems,
  partsOf,
  withPart,
  type FileInventory,
  type InventoryFile,
  type PersonalDataFinding,
} from "../src";

function file(path: string, overrides: Partial<InventoryFile> = {}): InventoryFile {
  return {
    file_path: path,
    file_size: 10,
    file_sha256: "0".repeat(64),
    file_identified_by: "signature",
    file_pronom_ids: ["fmt/1"],
    ...overrides,
  };
}

function scan(madeAt: string, paths: string[], limitations?: string[]): FileInventory {
  return {
    schema_class: "FileInventory",
    inventory_tool: "dd-inventory",
    inventory_tool_version: madeAt.slice(0, 4) === "2027" ? "0.2.0" : "0.1.0",
    inventory_identified_with: "fido",
    inventory_made_at: madeAt,
    inventory_files: paths.map((p) => file(p)),
    ...(limitations ? { inventory_limitations: limitations } : {}),
  };
}

const lab = scan("2026-11-01T09:00:00+00:00", ["a.csv", "notes/b.txt"], ["b.bin could not be read."]);
const instrument = scan("2026-11-02T09:00:00+00:00", ["run1.csv"]);

function paths(inventory: FileInventory): string[] {
  return (inventory.inventory_files ?? []).map((f) => f.file_path);
}

describe("parts", () => {
  it("names the folder an inventory already has, keeping what was said about its files", () => {
    const described = applyEdits(lab, edit(lab, NO_EDITS, { kind: "describe", path: "a.csv", text: "Soil" }));
    const named = asParts(described, "lab");
    expect(paths(named)).toEqual(["lab/a.csv", "lab/notes/b.txt"]);
    expect(named.inventory_files?.[0]?.file_description).toBe("Soil");
    expect(partsOf(named)?.map((p) => p.part_folder)).toEqual(["lab"]);
    expect(named.inventory_parts?.[0]?.part_limitations).toEqual(["b.bin could not be read."]);
    expect(named.inventory_limitations).toEqual(["In lab: b.bin could not be read."]);
    expect(partProblems(named)).toEqual([]);
    expect(asParts(named, "other")).toBe(named);
    expect(partsOf(lab)).toBeNull();
  });

  it("adds a folder and keeps the others as they were", () => {
    const both = withPart(asParts(lab, "lab"), instrument, "instrument");
    expect(paths(both)).toEqual(["instrument/run1.csv", "lab/a.csv", "lab/notes/b.txt"]);
    expect(both.inventory_parts?.map((p) => p.part_folder)).toEqual(["instrument", "lab"]);
    // The top level is the latest part's.
    expect(both.inventory_made_at).toBe(instrument.inventory_made_at);
    expect(partOf(both, "lab/notes/b.txt")?.part_folder).toBe("lab");
    expect(partProblems(both)).toEqual([]);
    expect(asInventory(JSON.parse(JSON.stringify(both)))).toEqual(both);
  });

  it("updates one folder whole, so only its files can be new, changed or gone", () => {
    const stored = withPart(asParts(lab, "lab"), instrument, "instrument");
    const described = applyEdits(
      stored,
      edit(stored, NO_EDITS, { kind: "describe", path: "lab/a.csv", text: "Soil" }),
    );
    const rescan = {
      ...scan("2027-01-05T09:00:00+00:00", ["run2.csv"]),
      inventory_files: [file("run1.csv", { file_sha256: "1".repeat(64) }), file("run2.csv")],
    };
    const updated = withPart(described, rescan, "instrument");
    const diff = diffInventories(described, updated);
    expect(diff.added).toEqual(["instrument/run2.csv"]);
    expect(diff.changed).toEqual(["instrument/run1.csv"]);
    expect(diff.removed).toEqual([]);
    expect(updated.inventory_files?.find((f) => f.file_path === "lab/a.csv")?.file_description).toBe("Soil");
    expect(updated.inventory_tool_version).toBe("0.2.0");
    expect(carryOver(described, updated).orphaned).toEqual([]);
  });

  it("refuses a folder inside one scanned whole, a bad name, and an inventory not yet named", () => {
    const stored = asParts(lab, "lab");
    expect(() => withPart(stored, instrument, "lab/notes")).toThrow(NotAPartFolder);
    expect(() => withPart(stored, instrument, "../up")).toThrow(NotAPartFolder);
    expect(() => withPart(lab, instrument, "instrument")).toThrow(NotAPartFolder);
    for (const bad of ["", "/a", "a/", "a//b", "a/./b"]) expect(partFolderProblem(bad)).not.toBeNull();
    expect(partFolderProblem("raw/2024")).toBeNull();
  });

  it("replaces the parts inside a folder scanned again as a whole", () => {
    const nested = withPart(asParts(lab, "site/lab"), instrument, "site/instrument");
    const whole = withPart(nested, scan("2027-02-01T00:00:00+00:00", ["x.csv"]), "site");
    expect(whole.inventory_parts?.map((p) => p.part_folder)).toEqual(["site"]);
    expect(paths(whole)).toEqual(["site/x.csv"]);
  });

  it("is refused when its folders do not fit its files", () => {
    const both = withPart(asParts(lab, "lab"), instrument, "instrument");
    const stray = { ...both, inventory_files: [...(both.inventory_files ?? []), file("elsewhere.csv")] };
    expect(partProblems(stray)).toHaveLength(1);
    expect(() => asInventory(stray)).toThrow(NotAnInventory);
  });
});

describe("personal-data findings in an inventory of folders", () => {
  const finding = (place: string): PersonalDataFinding => ({
    finding_kind: "email address",
    finding_file: place,
    finding_target: "text",
    finding_confidence: "high",
    finding_detector: "presidio",
  });
  const checked = (inventory: FileInventory, places: string[]): FileInventory => ({
    ...inventory,
    inventory_personal_data: places.map(finding),
  });

  it("moves each scan's findings under its folder, and lists every part's", () => {
    const named = asParts(checked(lab, ["notes/b.txt"]), "lab");
    expect(named.inventory_parts?.[0]?.part_personal_data).toEqual([finding("lab/notes/b.txt")]);
    const both = withPart(named, checked(instrument, []), "instrument");
    expect(both.inventory_parts?.map((p) => p.part_personal_data?.length)).toEqual([0, 1]);
    expect(both.inventory_personal_data).toEqual([finding("lab/notes/b.txt")]);
  });

  it("replaces a folder's findings when it is scanned again", () => {
    const named = asParts(checked(lab, ["notes/b.txt"]), "lab");
    const again = withPart(named, checked(lab, []), "lab");
    expect(again.inventory_personal_data).toEqual([]);
  });

  it("says no detector ran when any folder was scanned without one", () => {
    const named = asParts(checked(lab, ["notes/b.txt"]), "lab");
    const mixed = withPart(named, instrument, "instrument");
    expect(mixed.inventory_personal_data).toBeUndefined();
    expect(asInventory(JSON.parse(JSON.stringify(mixed)))).toEqual(mixed);
  });

  it("is refused when its findings are not a list of places", () => {
    const broken = { ...lab, inventory_personal_data: [{ finding_kind: "email address" }] };
    expect(() => asInventory(broken)).toThrow(NotAnInventory);
  });
});

describe("leaving parts out of an inventory of folders", () => {
  const both = withPart(asParts(lab, "lab"), instrument, "instrument");

  it("counts what was left out with its folder, and names none of it", () => {
    const left = omit(both, { paths: new Set(["lab/notes"]), columns: new Map() });
    const labPart = left.inventory_parts?.find((p) => p.part_folder === "lab");
    expect(paths(left)).toEqual(["instrument/run1.csv", "lab/a.csv"]);
    expect(labPart?.part_limitations?.some((s) => s.includes("left out 1 file"))).toBe(true);
    expect(JSON.stringify(left)).not.toContain("notes");
    // Updating the other folder keeps the count with its part.
    const updated = withPart(left, scan("2027-01-05T09:00:00+00:00", ["run1.csv"]), "instrument");
    expect(updated.inventory_limitations?.some((s) => s.startsWith("In lab: Before"))).toBe(true);
  });

  it("drops a folder left out whole and still counts it", () => {
    const left = omit(both, { paths: new Set(["instrument"]), columns: new Map() });
    expect(left.inventory_parts?.map((p) => p.part_folder)).toEqual(["lab"]);
    expect(left.inventory_limitations?.[0]).toContain("left out 1 file");
    expect(partProblems(left)).toEqual([]);
  });

  it("removes a limitation that names a file left out", () => {
    const withBin = withPart(both, scan("2027-01-01T00:00:00+00:00", ["a.csv", "b.bin"], ["b.bin could not be read."]), "lab");
    const left = omit(withBin, { paths: new Set(["lab/b.bin"]), columns: new Map() });
    expect(JSON.stringify(left)).not.toContain("b.bin");
  });
});
