import { describe, expect, it } from "vitest";

import {
  confidenceLabel,
  findingLabel,
  findingsByPlace,
  PERSONAL_DATA_TEXT,
  personalDataState,
  type FileInventory,
  type PersonalDataFinding,
} from "../src";

const base: FileInventory = {
  schema_class: "FileInventory",
  inventory_tool: "dd-inventory",
  inventory_tool_version: "0.1.0",
  inventory_made_at: "2026-11-18T09:00:00+00:00",
  inventory_files: [],
};

function finding(
  overrides: Partial<PersonalDataFinding>,
  without: (keyof PersonalDataFinding)[] = [],
): PersonalDataFinding {
  const made: Record<string, unknown> = {
    finding_kind: "email address",
    finding_file: "participants.csv",
    finding_target: "column",
    finding_column: "contact",
    finding_proportion: "over 50%",
    finding_confidence: "high",
    finding_detector: "presidio-analyzer",
    finding_examined: 200,
    ...overrides,
  };
  return Object.fromEntries(
    Object.entries(made).filter(([key]) => !without.includes(key as keyof PersonalDataFinding)),
  ) as unknown as PersonalDataFinding;
}

describe("personal-data findings", () => {
  it("tells an unchecked inventory from one where nothing was found", () => {
    expect(personalDataState(base)).toBe("not checked");
    expect(personalDataState({ ...base, inventory_personal_data: [] })).toBe("nothing found");
    expect(personalDataState({ ...base, inventory_personal_data: [finding({})] })).toBe("found");
    expect(new Set(Object.values(PERSONAL_DATA_TEXT)).size).toBe(3);
  });

  it("groups findings by the file or folder they concern, in order", () => {
    const findings = [
      finding({}),
      finding({ finding_kind: "phone number", finding_column: "telephone" }),
      finding({ finding_file: "consent/", finding_target: "file name", finding_kind: "direct identifier" }),
    ];
    const byPlace = findingsByPlace({ ...base, inventory_personal_data: findings });
    expect([...byPlace.keys()]).toEqual(["participants.csv", "consent/"]);
    expect(byPlace.get("participants.csv")).toHaveLength(2);
    expect(findingsByPlace(base).size).toBe(0);
  });

  it("puts each kind of finding into words that hold only its kind, column and bands", () => {
    const cases = [
      finding({}),
      finding({ finding_target: "field name", finding_kind: "direct identifier" }, ["finding_proportion"]),
      finding({ finding_target: "file name", finding_kind: "special category" }, ["finding_column"]),
      finding({ finding_target: "text" }, ["finding_column", "finding_proportion"]),
    ];
    const labels = cases.map(findingLabel);
    expect(new Set(labels).size).toBe(cases.length);
    expect(labels[0]).toContain("contact");
    expect(labels[1]).toContain("contact");
    for (const label of labels) {
      expect(label).not.toContain("presidio");
      expect(label).not.toContain("participants.csv");
    }
    expect(confidenceLabel(finding({}))).toContain("high");
  });
});
