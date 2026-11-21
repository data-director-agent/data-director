/**
 * Compare the inventory `dd-inventory` writes natively with the one it writes under Pyodide.
 * Pure. They must be equal but for when each was made, the runtime's local version label, which
 * only the Pyodide one has (docs/specs/projects.md), and table fields' summary values, which are
 * made natively only, with what each says about them (docs/specs/personal-data.md).
 */

/** Slots of a table field that only the native inventory has. */
const NATIVE_ONLY_FIELD_SLOTS = ["field_summary", "field_disclosure_check"];
/** The beginnings of the limitations that say what was done about summary values. */
const SUMMARY_LIMITATIONS = [
  "Summary values of table fields",
  "No summary values of table fields",
];

function withoutSummaries(value: Json): Json {
  if (Array.isArray(value)) {
    return value
      .filter(
        (v) =>
          typeof v !== "string" ||
          !(SUMMARY_LIMITATIONS.some((s) => v.startsWith(s)) || / summary values were computed /.test(v)),
      )
      .map(withoutSummaries);
  }
  if (isObject(value)) {
    return Object.fromEntries(
      Object.entries(value)
        .filter(([k]) => !NATIVE_ONLY_FIELD_SLOTS.includes(k))
        .map(([k, v]) => [k, withoutSummaries(v)]),
    );
  }
  return value;
}

export type Json = null | boolean | number | string | Json[] | { [key: string]: Json };

/** Every difference between two JSON values, one `path: native → pyodide` line each. */
export function differences(native: Json, pyodide: Json, path = "$"): string[] {
  if (Array.isArray(native) && Array.isArray(pyodide)) {
    const out: string[] = [];
    for (let i = 0; i < Math.max(native.length, pyodide.length); i++) {
      out.push(...differences(native[i] ?? null, pyodide[i] ?? null, `${path}[${i}]`));
    }
    return out;
  }
  if (isObject(native) && isObject(pyodide)) {
    const keys = [...new Set([...Object.keys(native), ...Object.keys(pyodide)])].sort();
    return keys.flatMap((k) => differences(native[k] ?? null, pyodide[k] ?? null, `${path}.${k}`));
  }
  return JSON.stringify(native) === JSON.stringify(pyodide)
    ? []
    : [`${path}: ${JSON.stringify(native)} → ${JSON.stringify(pyodide)}`];
}

function isObject(value: Json): value is { [key: string]: Json } {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/**
 * What differs between the two inventories beyond what may, given the runtime label Pyodide's
 * should carry (such as `pyodide.314.0.8`). Empty when the runtimes agree.
 */
export function parityProblems(
  native: Record<string, Json>,
  pyodide: Record<string, Json>,
  runtime: string,
): string[] {
  const expected = `${String(native.inventory_tool_version)}+${runtime}`;
  const problems =
    pyodide.inventory_tool_version === expected
      ? []
      : [
          `$.inventory_tool_version: expected ${JSON.stringify(expected)}, got ${JSON.stringify(pyodide.inventory_tool_version)}`,
        ];
  const strip = (inv: Record<string, Json>): Json => {
    const rest = { ...inv };
    delete rest.inventory_made_at;
    delete rest.inventory_tool_version;
    return rest;
  };
  return [
    ...problems,
    ...differences(withoutSummaries(strip(native)), withoutSummaries(strip(pyodide))),
  ];
}
