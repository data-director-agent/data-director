import soilSurvey from "./fixtures/soil-survey.inventory.json";

import {
  asInventory,
  describeInventory,
  files,
  folderTree,
  formatBytes,
  formatDate,
  formatFileCount,
  identificationLabel,
  looksLikeInventory,
  NotAnInventory,
  parseInventory,
  pronomUrl,
  searchFiles,
  summarise,
  type FileInventory,
  type FolderNode,
  type InventoryFile,
} from "../src";

const sample = asInventory(soilSurvey);

function file(path: string, overrides: Partial<InventoryFile> = {}): InventoryFile {
  return {
    file_path: path,
    file_size: 10,
    file_sha256: "0".repeat(64),
    file_identified_by: "signature",
    ...overrides,
  };
}

function inventory(list: InventoryFile[], overrides: Partial<FileInventory> = {}): FileInventory {
  return {
    schema_class: "FileInventory",
    inventory_files: list,
    inventory_tool: "dd-inventory",
    inventory_tool_version: "0.1.0",
    inventory_made_at: "2026-11-01T09:00:00+00:00",
    ...overrides,
  };
}

describe("parseInventory", () => {
  it("reads what dd-inventory writes", () => {
    const parsed = parseInventory(JSON.stringify(soilSurvey));
    expect(parsed.inventory_tool).toBe("dd-inventory");
    expect(files(parsed)).toHaveLength(soilSurvey.inventory_files.length);
  });

  it("says when the text is not JSON", () => {
    expect(() => parseInventory("not json")).toThrow(/not JSON/);
  });

  it.each([
    [[], /does not say it is a FileInventory/],
    [{ schema_class: "Other" }, /does not say it is a FileInventory/],
    [{ schema_class: "FileInventory", inventory_tool: "x", inventory_tool_version: "1" }, /no date/],
    [{ ...soilSurvey, inventory_files: {} }, /lists no files/],
    [{ ...soilSurvey, inventory_tool: undefined }, /which tool/],
    [{ ...soilSurvey, inventory_limitations: "one" }, /limitations/],
  ])("refuses %j", (value, message) => {
    expect(() => asInventory(value)).toThrow(NotAnInventory);
    expect(() => asInventory(value)).toThrow(message);
  });

  it.each([
    ["a string", /File 1 .* is not a description/],
    [{ ...file("a"), file_path: "" }, /has no path/],
    [{ ...file("a"), file_size: -1 }, /no size/],
    [{ ...file("a"), file_size: 1.5 }, /no size/],
    [{ ...file("a"), file_sha256: 1 }, /no digest/],
    [{ ...file("a"), file_identified_by: "magic" }, /how its format was identified/],
    [{ ...file("a"), file_media_type: 3 }, /media type/],
    [{ ...file("a"), file_pronom_ids: "fmt/1" }, /PRONOM/],
    [{ ...file("a"), file_fields: [{ field_type: "string" }] }, /without names/],
  ])("refuses a file that is %j", (bad, message) => {
    expect(() => asInventory(inventory([bad as InventoryFile]))).toThrow(message);
  });

  it("accepts an inventory with no files", () => {
    const empty = asInventory({ ...inventory([]), inventory_files: undefined });
    expect(files(empty)).toEqual([]);
  });

  it("tells pasted inventories from other text", () => {
    expect(looksLikeInventory(`  ${JSON.stringify(soilSurvey)}\n`)).toBe(true);
    expect(looksLikeInventory("please read FileInventory")).toBe(false);
  });
});

describe("summarise", () => {
  it("adds up the soil survey", () => {
    const summary = summarise(sample);
    expect(summary.fileCount).toBe(soilSurvey.inventory_files.length);
    expect(summary.bytes).toBe(soilSurvey.inventory_files.reduce((s, f) => s + f.file_size, 0));
    expect(summary.tables.map((t) => t.path)).toEqual(["data/readings.csv", "data/sites.tsv"]);
    expect(summary.tables[0]?.fields.map((f) => f.name)).toContain("ph");
    expect(summary.limitations).toEqual(soilSurvey.inventory_limitations);
    const total = Object.values(summary.identification).reduce((s, n) => s + n, 0);
    expect(total).toBe(summary.fileCount);
  });

  it("groups formats by media type, largest first, and finds doubtful files", () => {
    const summary = summarise(
      inventory([
        file("a.csv", { file_media_type: "text/csv", file_pronom_ids: ["x-fmt/18"], file_size: 5 }),
        file("b.csv", { file_media_type: "text/csv", file_pronom_ids: ["x-fmt/18", "fmt/1"], file_size: 5 }),
        file("c.bin", { file_identified_by: "none", file_size: 100 }),
      ]),
    );
    expect(summary.formats).toEqual([
      { mediaType: null, pronomIds: [], fileCount: 1, bytes: 100 },
      { mediaType: "text/csv", pronomIds: ["fmt/1", "x-fmt/18"], fileCount: 2, bytes: 10 },
    ]);
    expect(summary.ambiguous.map((f) => f.file_path)).toEqual(["b.csv"]);
    expect(summary.unknown.map((f) => f.file_path)).toEqual(["c.bin"]);
    expect(summary.identification).toEqual({ signature: 2, container: 0, extension: 0, none: 1 });
    expect(summary.limitations).toEqual([]);
  });
});

describe("folderTree", () => {
  it("nests files in folders, folders first, with totals", () => {
    const root = folderTree([
      file("z.txt"),
      file("data/raw/2.csv", { file_size: 2 }),
      file("data/raw/10.csv", { file_size: 3 }),
      file("data/b.csv"),
      file("a.txt"),
    ]);
    expect(root.fileCount).toBe(5);
    expect(root.bytes).toBe(35);
    expect(root.children.map((c) => c.name)).toEqual(["data", "a.txt", "z.txt"]);
    const data = root.children[0] as FolderNode;
    expect(data).toMatchObject({ path: "data", fileCount: 3, bytes: 15 });
    const raw = data.children[0] as FolderNode;
    expect(raw).toMatchObject({ path: "data/raw", fileCount: 2, bytes: 5 });
    expect(raw.children.map((c) => c.name)).toEqual(["2.csv", "10.csv"]);
    expect(raw.children[0]).toMatchObject({ kind: "file", path: "data/raw/2.csv" });
  });

  it("gives an empty root for no files", () => {
    expect(folderTree([])).toEqual({
      kind: "folder",
      name: "",
      path: "",
      children: [],
      fileCount: 0,
      bytes: 0,
    });
  });
});

describe("searchFiles", () => {
  const list = files(sample);

  it("matches paths, formats, PRONOM identifiers and columns, ignoring case", () => {
    expect(searchFiles(list, "PROTOCOL").map((f) => f.file_path)).toEqual(["docs/protocol.pdf"]);
    expect(searchFiles(list, "image/png").map((f) => f.file_path)).toEqual(["docs/site-map.png"]);
    expect(searchFiles(list, "x-fmt/13").map((f) => f.file_path)).toEqual(["data/sites.tsv"]);
    expect(searchFiles(list, "nitrate").map((f) => f.file_path)).toEqual(["data/readings.csv"]);
  });

  it("returns every file for an empty query", () => {
    expect(searchFiles(list, "  ")).toHaveLength(list.length);
  });
});

describe("formatting", () => {
  it.each([
    [0, "0 bytes"],
    [1, "1 byte"],
    [999, "999 bytes"],
    [1000, "1 kB"],
    [1234, "1.2 kB"],
    [999_950, "1 MB"],
    [3_400_000_000, "3.4 GB"],
    [5e18, "5,000 PB"],
  ])("formats %d bytes as %s", (bytes, text) => {
    expect(formatBytes(bytes)).toBe(text);
  });

  it("counts files", () => {
    expect(formatFileCount(1)).toBe("1 file");
    expect(formatFileCount(1200)).toBe("1,200 files");
  });

  it("describes an inventory", () => {
    expect(describeInventory(42, "2026-11-01T09:00:00Z")).toBe("42 files, made 1 Nov 2026");
    expect(describeInventory(1, "not a date")).toBe("1 file");
    expect(formatDate("not a date")).toBeNull();
  });

  it("names identification methods and PRONOM pages", () => {
    expect(identificationLabel("signature")).toBe("Recognised from its content");
    expect(identificationLabel("none")).toBe("Not recognised");
    expect(pronomUrl("fmt/18")).toBe("https://www.nationalarchives.gov.uk/PRONOM/fmt/18");
  });
});
