import {
  applyEdits,
  asInventory,
  canChooseFormat,
  carryOver,
  countEdits,
  DESCRIPTION_LIMIT,
  describeEdits,
  diffInventories,
  edit,
  NO_EDITS,
  omit,
  type EditAction,
  type FileInventory,
  type InventoryEdits,
  type InventoryFile,
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

const empty: FileInventory = {
  schema_class: "FileInventory",
  inventory_tool: "dd-inventory",
  inventory_tool_version: "0.1.0",
  inventory_made_at: "2026-11-01T09:00:00+00:00",
};

function undescribed(f: InventoryFile): InventoryFile {
  const copy = { ...f };
  delete copy.file_description;
  return copy;
}

const base: FileInventory = {
  ...empty,
  inventory_files: [
    file("README.md", { file_description: "How the survey was run" }),
    file("data/soil.csv", {
      file_identified_by: "extension",
      file_pronom_ids: ["x-fmt/18"],
      file_media_type: "text/csv",
      file_fields: [
        { name: "site", field_type: "string" },
        { name: "ph", field_type: "number", field_description: "Acidity" },
      ],
    }),
    file("data/scan.tif", { file_pronom_ids: ["fmt/353", "fmt/154"] }),
    file("data/blob.bin", { file_identified_by: "none", file_pronom_ids: [] }),
    file("code/clean.py", { file_role: "code" }),
  ],
};

function run(...actions: EditAction[]): InventoryEdits {
  return actions.reduce((edits, action) => edit(base, edits, action), NO_EDITS);
}

function found(inventory: FileInventory, path: string): InventoryFile | undefined {
  return inventory.inventory_files?.find((f) => f.file_path === path);
}

describe("applyEdits", () => {
  it("returns the inventory itself when nothing changes", () => {
    expect(applyEdits(base, NO_EDITS)).toBe(base);
    expect(describeEdits(countEdits(base, NO_EDITS))).toBeNull();
  });

  it("leaves things out exactly as omit does", () => {
    const edits = run(
      { kind: "omit", path: "code" },
      { kind: "omit-column", path: "data/soil.csv", column: "site" },
    );
    expect(applyEdits(base, edits)).toEqual(omit(base, edits.omitted));
  });

  it("writes statements beside the facts and never changes the base", () => {
    const before = JSON.parse(JSON.stringify(base)) as FileInventory;
    const edits = run(
      { kind: "describe", path: "data/soil.csv", text: "  Soil readings by site  " },
      { kind: "role", paths: ["data/soil.csv", "data/scan.tif"], role: "data" },
      { kind: "format", path: "data/scan.tif", format: { pronomId: "fmt/353", mediaType: "image/tiff" } },
      { kind: "describe-column", path: "data/soil.csv", column: "site", text: "Site code" },
      { kind: "describe-column", path: "data/soil.csv", column: "ph", text: "" },
    );
    const edited = applyEdits(base, edits);
    expect(base).toEqual(before);

    const soil = found(edited, "data/soil.csv");
    expect(soil).toMatchObject({ file_description: "Soil readings by site", file_role: "data" });
    expect(soil?.file_sha256).toBe(found(base, "data/soil.csv")?.file_sha256);
    expect(soil?.file_fields).toEqual([
      { name: "site", field_type: "string", field_description: "Site code" },
      { name: "ph", field_type: "number" },
    ]);
    expect(found(edited, "data/scan.tif")).toMatchObject({
      file_pronom_ids: ["fmt/353"],
      file_media_type: "image/tiff",
      file_identified_by: "researcher",
    });
    expect(() => asInventory(JSON.parse(JSON.stringify(edited)))).not.toThrow();
    expect(describeEdits(countEdits(base, edits))).toBe("3 descriptions; 2 roles; 1 format chosen");
  });

  it("clears a description or a role the document held", () => {
    const edited = applyEdits(
      base,
      run(
        { kind: "describe", path: "README.md", text: "" },
        { kind: "role", paths: ["code/clean.py"], role: null },
      ),
    );
    expect(found(edited, "README.md")).not.toHaveProperty("file_description");
    expect(found(edited, "code/clean.py")).not.toHaveProperty("file_role");
  });

  it("does not count statements about what is left out", () => {
    const edits = run(
      { kind: "describe", path: "code/clean.py", text: "Cleaning" },
      { kind: "describe-column", path: "data/soil.csv", column: "site", text: "Site code" },
      { kind: "omit", path: "code" },
      { kind: "omit-column", path: "data/soil.csv", column: "site" },
    );
    expect(countEdits(base, edits)).toMatchObject({ omittedFiles: 1, omittedColumns: 1, descriptions: 0 });
    expect(describeEdits(countEdits(base, edits))).toBe("1 file and 1 column left out");
    expect(JSON.stringify(applyEdits(base, edits))).not.toContain("Cleaning");
  });
});

describe("edit", () => {
  it("keeps only real changes", () => {
    expect(run({ kind: "describe", path: "README.md", text: "How the survey was run " })).toEqual(NO_EDITS);
    expect(run({ kind: "role", paths: ["code/clean.py"], role: "code" })).toEqual(NO_EDITS);
    expect(run({ kind: "describe", path: "data/soil.csv", text: "x" }, { kind: "describe", path: "data/soil.csv", text: "" })).toEqual(
      NO_EDITS,
    );
    expect(run({ kind: "omit", path: "code" }, { kind: "include", path: "code" }).omitted.paths.size).toBe(0);
    const columns = run(
      { kind: "omit-column", path: "data/soil.csv", column: "site" },
      { kind: "include-column", path: "data/soil.csv", column: "site" },
    );
    expect(columns.omitted.columns.size).toBe(0);
    expect(
      run(
        { kind: "describe-column", path: "data/soil.csv", column: "site", text: "x" },
        { kind: "describe-column", path: "data/soil.csv", column: "site", text: "" },
      ).fields.size,
    ).toBe(0);
    expect(run({ kind: "format", path: "data/scan.tif", format: null })).toEqual(NO_EDITS);
  });

  it("returns the same edits for an action that changes nothing", () => {
    const once = run({ kind: "omit", path: "code" });
    expect(edit(base, once, { kind: "omit", path: "code" })).toBe(once);
    expect(edit(base, once, { kind: "include-column", path: "data/soil.csv", column: "x" })).toBe(once);
    expect(edit(base, once, { kind: "role", paths: ["missing"], role: "data" })).toBe(once);
    const chosen = edit(base, once, { kind: "format", path: "data/scan.tif", format: { pronomId: "fmt/154" } });
    expect(edit(base, chosen, { kind: "format", path: "data/scan.tif", format: { pronomId: "fmt/154" } })).toBe(chosen);
  });

  it("ignores paths and columns the inventory does not list", () => {
    expect(
      run(
        { kind: "describe", path: "nowhere.txt", text: "x" },
        { kind: "format", path: "nowhere.txt", format: { mediaType: "text/plain" } },
        { kind: "describe-column", path: "data/soil.csv", column: "depth", text: "x" },
        { kind: "role", paths: ["data/soil.csv"], role: "secret" as never },
      ),
    ).toEqual(NO_EDITS);
  });

  it("lets a format be chosen only where the command could not tell", () => {
    const files = base.inventory_files ?? [];
    expect(files.filter(canChooseFormat).map((f) => f.file_path)).toEqual([
      "data/soil.csv",
      "data/scan.tif",
      "data/blob.bin",
    ]);
    const refused: EditAction[] = [
      { kind: "format", path: "README.md", format: { mediaType: "text/markdown" } },
      { kind: "format", path: "data/scan.tif", format: { pronomId: "fmt/999" } },
      { kind: "format", path: "data/blob.bin", format: { mediaType: "not a type" } },
      { kind: "format", path: "data/blob.bin", format: { mediaType: "  " } },
    ];
    for (const action of refused) expect(run(action)).toEqual(NO_EDITS);
    const chosen = applyEdits(base, run({ kind: "format", path: "data/blob.bin", format: { mediaType: " application/x-hdf5 " } }));
    expect(found(chosen, "data/blob.bin")).toMatchObject({
      file_media_type: "application/x-hdf5",
      file_pronom_ids: [],
      file_identified_by: "researcher",
    });
  });

  it("keeps a description within the limit", () => {
    const edits = run({ kind: "describe", path: "data/soil.csv", text: "x".repeat(DESCRIPTION_LIMIT + 5) });
    expect(edits.files.get("data/soil.csv")?.description).toHaveLength(DESCRIPTION_LIMIT);
  });
});

describe("diffInventories", () => {
  it("names what is new, gone and changed", () => {
    const rescan: FileInventory = {
      ...base,
      inventory_files: [
        file("README.md", { file_sha256: "1".repeat(64) }),
        file("data/soil.csv"),
        file("data/scan.tif"),
        file("data/new.csv"),
      ],
    };
    expect(diffInventories(base, rescan)).toEqual({
      added: ["data/new.csv"],
      removed: ["code/clean.py", "data/blob.bin"],
      changed: ["README.md"],
      unchanged: 2,
    });
    expect(diffInventories(empty, empty)).toEqual({
      added: [],
      removed: [],
      changed: [],
      unchanged: 0,
    });
  });
});

describe("carryOver", () => {
  const stored = applyEdits(
    base,
    run(
      { kind: "role", paths: ["data/soil.csv"], role: "data" },
      { kind: "format", path: "data/scan.tif", format: { pronomId: "fmt/353" } },
      { kind: "format", path: "data/blob.bin", format: { mediaType: "application/x-hdf5" } },
      { kind: "describe-column", path: "data/soil.csv", column: "site", text: "Site code" },
    ),
  );

  it("states again what the researcher said, by path", () => {
    const rescan: FileInventory = {
      ...base,
      inventory_made_at: "2026-11-09T09:00:00+00:00",
      inventory_files: (base.inventory_files ?? [])
        .filter((f) => f.file_path !== "code/clean.py")
        .map((f) => (f.file_path === "data/blob.bin" ? { ...f, file_sha256: "2".repeat(64) } : f))
        .map((f) => (f.file_path === "README.md" ? undescribed(f) : f)),
    };
    const { edits, orphaned } = carryOver(stored, rescan);
    expect(orphaned).toEqual(["code/clean.py"]);
    const edited = applyEdits(rescan, edits);
    expect(found(edited, "README.md")?.file_description).toBe("How the survey was run");
    expect(found(edited, "data/soil.csv")?.file_role).toBe("data");
    expect(found(edited, "data/soil.csv")?.file_fields?.[0]?.field_description).toBe("Site code");
    expect(found(edited, "data/scan.tif")).toMatchObject({ file_pronom_ids: ["fmt/353"], file_identified_by: "researcher" });
    // The file changed, so the format chosen for it before may no longer be right.
    expect(found(edited, "data/blob.bin")?.file_identified_by).toBe("none");
  });

  it("carries nothing from an inventory with no statements", () => {
    const plain: FileInventory = { ...base, inventory_files: [file("a.txt")] };
    expect(carryOver(plain, base)).toEqual({ edits: NO_EDITS, orphaned: [] });
    expect(carryOver(empty, base).edits).toEqual(NO_EDITS);
  });
});
