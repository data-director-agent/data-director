import { describe, expect, it } from "vitest";
import { fieldValues, hasSuppressed, suppressedText, type TableField } from "../src/index";

const check = {
  check_tool: "acro",
  check_tool_version: "1.1.0",
  check_threshold: 10,
  check_rounding_base: 5,
  check_suppressed: 0,
};

describe("field values", () => {
  it("has none for a field without a summary", () => {
    expect(fieldValues({ name: "x" })).toEqual([]);
    expect(hasSuppressed({ name: "x" })).toBe(false);
  });

  it("says each value in a fixed order, and never calls a range the minimum and maximum", () => {
    const field: TableField = {
      name: "age",
      field_type: "integer",
      field_summary: {
        summary_rows_read: 200,
        summary_null_count: 15,
        summary_range_low: "27",
        summary_range_high: "62",
        summary_mean: 44.752941,
        summary_missing_codes: [{ missing_code: "-99", missing_code_count: 30 }],
      },
      field_disclosure_check: check,
    };
    expect(fieldValues(field)).toEqual([
      "27 to 62, extremes left out",
      "mean 44.75",
      "-99 in 30 rows",
      "15 empty",
    ]);
  });

  it("lists categories with their counts", () => {
    const field: TableField = {
      name: "diagnosis",
      field_summary: { summary_categories: [{ category_value: "eczema", category_count: 70 }] },
      field_disclosure_check: { ...check, check_suppressed: 1 },
    };
    expect(fieldValues(field)).toEqual(["eczema (70)"]);
    expect(hasSuppressed(field)).toBe(true);
  });

  it("says why values were left out in the spec's words", () => {
    expect(suppressedText(10)).toBe(
      "Some summary values were left out because fewer than 10 records shared them. They are not stored anywhere.",
    );
  });
});
