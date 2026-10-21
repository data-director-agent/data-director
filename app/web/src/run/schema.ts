/**
 * Reading a class's JSON Schema (as `dd-gen-schema` writes it, ADR-0020) for its shape: what the
 * run form asks for and how a result is laid out. Presentation comes from the schema and the
 * manifest's derivations, never from a per-agent layout (ADR-0016).
 *
 * Only the shapes the generated schemas use are recognised: `$ref` into `$defs`, `anyOf` with
 * null, nullable `type` arrays, enums, arrays and objects. Anything else is "other".
 */

export interface JsonSchema {
  type?: string | string[];
  $ref?: string;
  $defs?: Record<string, JsonSchema>;
  items?: JsonSchema;
  anyOf?: JsonSchema[];
  properties?: Record<string, JsonSchema>;
  required?: string[];
  enum?: unknown[];
  title?: string;
  description?: string;
}

export type ScalarType = "string" | "number" | "integer" | "boolean";

export type Shape =
  | { kind: "scalar"; type: ScalarType; options?: string[] }
  | { kind: "list"; item: ScalarType }
  | { kind: "records"; schema: JsonSchema }
  | { kind: "object"; schema: JsonSchema }
  | { kind: "other" };

const SCALARS: readonly string[] = ["string", "number", "integer", "boolean"];

/** Follow a `$ref` into the root's `$defs`, and drop the null branch of an `anyOf`. */
export function resolve(root: JsonSchema, schema: JsonSchema): JsonSchema {
  let current = schema;
  for (let depth = 0; depth < 8; depth++) {
    if (current.$ref?.startsWith("#/$defs/")) {
      const found = root.$defs?.[current.$ref.slice("#/$defs/".length)];
      if (!found) return {};
      current = { ...found, ...(current.description ? { description: current.description } : {}) };
      continue;
    }
    const branches = current.anyOf?.filter((b) => !(b.type === "null"));
    if (branches?.length === 1 && branches[0]) {
      current = branches[0];
      continue;
    }
    return current;
  }
  return current;
}

function types(schema: JsonSchema): string[] {
  const given = schema.type === undefined ? [] : [schema.type].flat();
  return given.filter((t) => t !== "null");
}

export function shapeOf(root: JsonSchema, schema: JsonSchema): Shape {
  const resolved = resolve(root, schema);
  const [type] = types(resolved);
  if (resolved.enum && resolved.enum.every((v) => typeof v === "string")) {
    return { kind: "scalar", type: "string", options: resolved.enum as string[] };
  }
  if (type && SCALARS.includes(type)) return { kind: "scalar", type: type as ScalarType };
  if (type === "array" && resolved.items) {
    const item = resolve(root, resolved.items);
    const [itemType] = types(item);
    if (item.enum || (itemType && SCALARS.includes(itemType))) {
      return { kind: "list", item: (itemType ?? "string") as ScalarType };
    }
    if (item.properties) return { kind: "records", schema: item };
    return { kind: "other" };
  }
  if (resolved.properties) return { kind: "object", schema: resolved };
  return { kind: "other" };
}

/** A class's properties in schema order, without the `schema_class` designator. */
export function properties(schema: JsonSchema): [string, JsonSchema][] {
  return Object.entries(schema.properties ?? {}).filter(([name]) => name !== "schema_class");
}
