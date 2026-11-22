/**
 * Writes `src/api/generated/responses.ts`, the TypeScript types of the app's responses, from the JSON Schema
 * of its response models (`python -m dd_app.responses`, app/src/dd_app/responses.py), read on
 * standard input. Run it as `npm run gen:api` (docs/specs/app.md, "API types"); CI fails when the
 * checked-in file is not what this writes.
 *
 * A model whose shape another package defines names its TypeScript type with `tsType`
 * (app/src/dd_app/contract_shapes.py). `IMPORTS` says where the shell already has each; a name it
 * does not list fails, so a new one is given its home here rather than an `any`.
 */

import { Buffer } from "node:buffer";
import { writeFileSync } from "node:fs";
import process from "node:process";
import { URL } from "node:url";
import { compile } from "json-schema-to-typescript";

const OUTPUT = new URL("../src/api/generated/responses.ts", import.meta.url);

/** Where each `tsType` name is defined, as `responses.ts` imports it. */
const IMPORTS = {
  DocumentQuestion: "../contract",
  DocumentVersionRef: "../contract",
  Envelope: "@data-director/agent-view",
  InvocationRequest: "../contract",
  Principal: "../contract",
  ProjectFact: "../../project/facts",
  Question: "../../conversation/question",
  RawModelUse: "@data-director/agent-view",
  RawSchemaEntry: "@data-director/agent-view",
  RawSkillUse: "@data-director/agent-view",
  RawToolUse: "@data-director/agent-view",
  ResearcherRecord: "../../project/researcher",
};

const HEADER = `/**
 * The bodies the app's routes answer with, as TypeScript (docs/specs/app.md, "API types").
 *
 * Generated from the app's response models (app/src/dd_app/responses.py) by
 * app/web/scripts/gen-api-types.mjs. Do not edit: change the models and run, in app/web,
 *
 *     npm run gen:api
 *
 * CI fails when this file is not what the models generate.
 */
`;

/**
 * `node` with each `$ref` that has keys beside it (a field's description) put in an `allOf`:
 * json-schema-to-typescript would otherwise declare a second copy of the referenced type.
 */
function loneRefs(node) {
  if (Array.isArray(node)) return node.map(loneRefs);
  if (node === null || typeof node !== "object") return node;
  const out = Object.fromEntries(Object.entries(node).map(([key, value]) => [key, loneRefs(value)]));
  if (typeof out.$ref === "string" && Object.keys(out).length > 1) {
    const { $ref, ...rest } = out;
    return { ...rest, allOf: [{ $ref }] };
  }
  return out;
}

/** Every `tsType` named anywhere in `node`, sorted. */
function tsTypes(node, found = new Set()) {
  if (Array.isArray(node)) node.forEach((item) => tsTypes(item, found));
  else if (node !== null && typeof node === "object") {
    if (typeof node.tsType === "string") found.add(node.tsType);
    Object.values(node).forEach((value) => tsTypes(value, found));
  }
  return [...found].sort();
}

/** The `import type` lines for `names`, one per module, in a fixed order. */
function importLines(names) {
  const unknown = names.filter((name) => !(name in IMPORTS));
  if (unknown.length > 0) {
    throw new Error(`No home for tsType ${unknown.join(", ")}: add it to IMPORTS in gen-api-types.mjs.`);
  }
  const byModule = new Map();
  for (const name of names) {
    const module = IMPORTS[name];
    byModule.set(module, [...(byModule.get(module) ?? []), name]);
  }
  return [...byModule.keys()]
    .sort()
    .map((module) => `import type { ${byModule.get(module).join(", ")} } from "${module}";`)
    .join("\n");
}

/** Standard input, whole: a pipe is read as it arrives. */
async function stdin() {
  const chunks = [];
  for await (const chunk of process.stdin) chunks.push(chunk);
  return Buffer.concat(chunks).toString("utf8");
}

const schema = JSON.parse(await stdin());
const defs = loneRefs(schema.$defs);
const root = {
  title: "AppResponse",
  description: "Any body the app sends.",
  anyOf: Object.keys(defs)
    .sort()
    .map((name) => ({ $ref: `#/$defs/${name}` })),
  $defs: defs,
};
const body = await compile(root, "AppResponse", {
  bannerComment: "",
  additionalProperties: false,
  unknownAny: true,
  strictIndexSignatures: false,
  format: true,
});
writeFileSync(OUTPUT, `${HEADER}\n${importLines(tsTypes(defs))}\n\n${body}`);
