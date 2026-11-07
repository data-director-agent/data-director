import {
  countOmitted,
  describeOmitted,
  isOmitted,
  NOTHING_OMITTED,
  omit,
  type FileInventory,
  type InventoryFile,
} from "../src";

function file(path: string, fields: string[] = []): InventoryFile {
  return {
    file_path: path,
    file_size: 10,
    file_sha256: "0".repeat(64),
    file_identified_by: "signature",
    ...(fields.length ? { file_fields: fields.map((name) => ({ name, field_type: "string" })) } : {}),
  };
}

const sample: FileInventory = {
  schema_class: "FileInventory",
  inventory_tool: "dd-inventory",
  inventory_tool_version: "0.1.0",
  inventory_made_at: "2026-11-01T09:00:00+00:00",
  inventory_files: [
    file("README.md"),
    file("participants/alice-smith.csv", ["id", "participant_name", "hiv_status"]),
    file("participants/bob-jones.csv", ["id"]),
    file("data/readings.csv", ["site", "participant_name", "ph"]),
  ],
  inventory_limitations: [
    "participants/bob-jones.csv could not be read: Permission denied.",
    "Table fields are inferred from a sample of rows; a later row may not fit the type given.",
  ],
};

describe("omit", () => {
  it("returns the inventory as it is when nothing is left out", () => {
    expect(omit(sample, NOTHING_OMITTED)).toBe(sample);
    expect(describeOmitted(countOmitted(sample, NOTHING_OMITTED))).toBeNull();
  });

  it("leaves out a file, a folder and a column, and names none of them", () => {
    const omission = {
      paths: new Set(["README.md", "participants"]),
      columns: new Map([["data/readings.csv", new Set(["participant_name"])]]),
    };
    expect(countOmitted(sample, omission)).toEqual({ files: 3, columns: 1 });
    const trimmed = omit(sample, omission);
    expect(trimmed.inventory_files?.map((f) => f.file_path)).toEqual(["data/readings.csv"]);
    expect(trimmed.inventory_files?.[0]?.file_fields?.map((f) => f.name)).toEqual(["site", "ph"]);
    const text = JSON.stringify(trimmed);
    for (const secret of ["README.md", "participants", "alice-smith", "participant_name", "hiv_status"]) {
      expect(text).not.toContain(secret);
    }
    expect(trimmed.inventory_limitations).toEqual([
      "Table fields are inferred from a sample of rows; a later row may not fit the type given.",
      "Before this inventory was added, the researcher left out 3 files and 1 column. That they " +
        "are not listed here does not mean they are not in the dataset.",
    ]);
    // The original is untouched.
    expect(sample.inventory_files).toHaveLength(4);
  });

  it("counts only columns a kept table has", () => {
    const omission = {
      paths: new Set(["participants"]),
      columns: new Map([
        ["participants/alice-smith.csv", new Set(["hiv_status"])],
        ["data/readings.csv", new Set(["nothing-by-this-name"])],
      ]),
    };
    expect(countOmitted(sample, omission)).toEqual({ files: 2, columns: 0 });
    expect(describeOmitted({ files: 1, columns: 2 })).toBe("1 file and 2 columns");
  });

  it("tells a folder from a name that starts the same way", () => {
    const paths = new Set(["data"]);
    expect(isOmitted("data/readings.csv", paths)).toBe(true);
    expect(isOmitted("data-old/readings.csv", paths)).toBe(false);
    expect(isOmitted("database.csv", paths)).toBe(false);
  });
});
