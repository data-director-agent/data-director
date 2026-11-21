/**
 * A table field's summary values in words, for a person (docs/specs/personal-data.md, #611).
 * Pure. The inventory command writes only values that passed disclosure control, so each phrase
 * here is one the researcher's computer already judged safe to show.
 */

import type { TableField } from "./types";

/** What the app says of a field some of whose summary values were left out, in the spec's words. */
export function suppressedText(threshold: number): string {
  return (
    `Some summary values were left out because fewer than ${threshold} records shared them. ` +
    "They are not stored anywhere."
  );
}

function round(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toPrecision(4).replace(/\.?0+$/, "");
}

/**
 * The field's summary values as short phrases, such as `27 to 62, extremes left out`, `mean 44.75`, `-99 in 30 rows`,
 * in a fixed order. Empty when the field has none.
 */
export function fieldValues(field: TableField): string[] {
  const s = field.field_summary;
  if (!s) return [];
  const out: string[] = [];
  if (s.summary_range_low !== undefined && s.summary_range_high !== undefined) {
    // Not the minimum and maximum: at least the threshold's number of rows lie beyond each.
    out.push(`${s.summary_range_low} to ${s.summary_range_high}, extremes left out`);
  }
  if (s.summary_mean !== undefined) out.push(`mean ${round(s.summary_mean)}`);
  for (const c of s.summary_categories ?? []) out.push(`${c.category_value} (${c.category_count})`);
  for (const m of s.summary_missing_codes ?? []) {
    out.push(`${m.missing_code} in ${m.missing_code_count} rows`);
  }
  if (s.summary_null_count !== undefined) out.push(`${s.summary_null_count} empty`);
  return out;
}

/** Whether the field's check left any summary value out. */
export function hasSuppressed(field: TableField): boolean {
  return (field.field_disclosure_check?.check_suppressed ?? 0) > 0;
}
