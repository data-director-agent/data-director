import { describe, expect, it } from "vitest";

import { fileHints, HINT_LABELS, HINT_RULES, type FileInventory, type InventoryFile } from "../src";

let next = 0;

function file(path: string, overrides: Partial<InventoryFile> = {}): InventoryFile {
  next += 1;
  return {
    file_path: path,
    file_size: 10,
    file_sha256: next.toString(16).padStart(64, "0"),
    file_identified_by: "extension",
    ...overrides,
  };
}

function inventory(list: InventoryFile[]): FileInventory {
  return {
    schema_class: "FileInventory",
    inventory_files: list,
    inventory_tool: "dd-inventory",
    inventory_tool_version: "0.1.0",
    inventory_made_at: "2026-11-16T00:00:00+00:00",
  };
}

const fields = (...names: string[]) => names.map((name) => ({ name, field_type: "string" }));
const copy = "7".repeat(64);

/** Shaped like dataset A of data-director-agent/sample-data, whose problems are in contents. */
const moorland = inventory([
  file("analysis/plot_temp_gradient.R"),
  file("calibration/sites.csv", { file_fields: fields("node", "lat", "lon", "elev") }),
  file("data/N01-N06_v3.csv", { file_fields: fields("timestamp_utc", "node_id", "ta", "rh") }),
  file("data/Thumbs.db", { file_size: 0 }),
  file("data/logger_export.csv", { file_sha256: copy }),
  file("data/old/logger_export (copy).csv", { file_sha256: copy }),
  file("fieldnotes/fieldnotes_2024.txt"),
  file("governance/landowner-access-agreement.md"),
  file("reference/WeatherNest_Stn442_hourly.csv"),
]);

const kinds = (inv: FileInventory) =>
  [...fileHints(inv)].flatMap(([path, hints]) => hints.map((h) => [path, h.kind]));

describe("fileHints", () => {
  it("marks the files whose names, size or digest call for a person to look", () => {
    expect(kinds(moorland)).toEqual(
      expect.arrayContaining([
        ["calibration/sites.csv", "coordinates"],
        ["data/Thumbs.db", "system_file"],
        ["data/Thumbs.db", "empty"],
        ["data/logger_export.csv", "duplicate"],
        ["data/old/logger_export (copy).csv", "duplicate"],
        ["fieldnotes/fieldnotes_2024.txt", "free_text"],
        ["governance/landowner-access-agreement.md", "governance"],
        ["reference/WeatherNest_Stn442_hourly.csv", "third_party"],
      ]),
    );
    const hinted = fileHints(moorland);
    expect(hinted.has("analysis/plot_temp_gradient.R")).toBe(false);
    expect(hinted.has("data/N01-N06_v3.csv")).toBe(false);
  });

  it("names each copy of a duplicate, and does not count empty files as copies", () => {
    const inv = inventory([
      file("a.csv", { file_sha256: copy }),
      file("b/a.csv", { file_sha256: copy }),
      file("x.txt", { file_size: 0, file_sha256: "e".repeat(64) }),
      file("y.txt", { file_size: 0, file_sha256: "e".repeat(64) }),
    ]);
    const hints = fileHints(inv);
    expect(hints.get("a.csv")?.[0]?.related).toEqual(["b/a.csv"]);
    expect(hints.get("x.txt")?.map((h) => h.kind)).toEqual(["empty"]);
  });

  it.each(["notes_lat.csv", "translation.txt", "logger_export.csv", "longitudinal.csv"])(
    "matches whole words only, in %s",
    (name) => {
      const inv = inventory([file(`data/${name}`, { file_fields: fields("translated", "plateau") })]);
      const found = (fileHints(inv).get(`data/${name}`) ?? []).map((h) => h.kind);
      expect(found).not.toContain("coordinates");
      expect(found.includes("free_text")).toBe(name.startsWith("notes"));
    },
  );

  it("gives every kind a label and a question", () => {
    for (const rule of HINT_RULES) {
      expect(HINT_LABELS[rule.kind]).toBeTruthy();
      expect(rule.question).toBeTruthy();
    }
  });
});
