import { className, fieldName, type JsonSchema, properties, resolve, shapeOf } from "../src";

const ROOT: JsonSchema = {
  $defs: {
    Kind: { type: "string", enum: ["a_b", "c"] },
    Row: { type: "object", properties: { x: { type: "integer" } } },
  },
};

describe("shapeOf", () => {
  it.each<[JsonSchema, string]>([
    [{ type: "string" }, "scalar"],
    [{ type: ["integer", "null"] }, "scalar"],
    [{ $ref: "#/$defs/Kind" }, "scalar"],
    [{ anyOf: [{ $ref: "#/$defs/Row" }, { type: "null" }] }, "object"],
    [{ type: "array", items: { type: "string" } }, "list"],
    [{ type: "array", items: { $ref: "#/$defs/Kind" } }, "list"],
    [{ type: "array", items: { $ref: "#/$defs/Row" } }, "records"],
    [{ type: "array", items: { type: "array" } }, "other"],
    [{ $ref: "#/$defs/Missing" }, "other"],
    [{}, "other"],
  ])("reads %j as %s", (schema, kind) => {
    expect(shapeOf(ROOT, schema).kind).toBe(kind);
  });

  it("keeps a reference's own description", () => {
    expect(resolve(ROOT, { $ref: "#/$defs/Row", description: "here" }).description).toBe("here");
  });

  it("leaves out the schema_class designator", () => {
    expect(properties({ properties: { schema_class: {}, a: {} } }).map(([n]) => n)).toEqual(["a"]);
  });
});

describe("wording", () => {
  it("puts names into words", () => {
    expect(className("DatasetProfile")).toBe("dataset profile");
    expect(fieldName("media_types")).toBe("Media types");
    expect(fieldName("soil-chemistry.profile")).toBe("Soil chemistry profile");
  });
});
