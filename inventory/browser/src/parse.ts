/**
 * Reading a document as a `FileInventory`. The check is structural, enough to display the
 * document safely and to tell a researcher plainly why a file is not an inventory; the server
 * still checks it against the contract's class schema before a project keeps it.
 */

import { IDENTIFICATION_METHODS, type FileInventory } from "./types";

/** A document that is not an inventory; the message is a sentence a researcher can read. */
export class NotAnInventory extends Error {
  override name = "NotAnInventory";
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isStringList(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === "string");
}

/** Whether text looks like a whole inventory, as when one is pasted rather than attached. */
export function looksLikeInventory(text: string): boolean {
  const trimmed = text.trim();
  return trimmed.startsWith("{") && trimmed.includes('"FileInventory"');
}

/** `text` read as JSON and then as an inventory (`asInventory`). */
export function parseInventory(text: string): FileInventory {
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch {
    throw new NotAnInventory("This file is not JSON, so it is not an inventory.");
  }
  return asInventory(parsed);
}

/** `value` as an inventory, or `NotAnInventory` saying what is wrong with it. */
export function asInventory(value: unknown): FileInventory {
  if (!isRecord(value) || value.schema_class !== "FileInventory") {
    throw new NotAnInventory(
      "This file is not an inventory: it does not say it is a FileInventory, as the file " +
        "dd-inventory writes does.",
    );
  }
  const files = value.inventory_files;
  if ((files !== undefined && !Array.isArray(files)) || typeof value.inventory_made_at !== "string") {
    throw new NotAnInventory("This inventory is incomplete: it lists no files or no date.");
  }
  if (typeof value.inventory_tool !== "string" || typeof value.inventory_tool_version !== "string") {
    throw new NotAnInventory("This inventory does not say which tool made it.");
  }
  if (value.inventory_limitations !== undefined && !isStringList(value.inventory_limitations)) {
    throw new NotAnInventory("This inventory's limitations are not a list of sentences.");
  }
  (files ?? []).forEach((file: unknown, index: number) => checkFile(file, index + 1));
  return value as unknown as FileInventory;
}

function checkFile(file: unknown, position: number): void {
  const problem = fileProblem(file);
  if (problem) throw new NotAnInventory(`File ${position} of this inventory ${problem}.`);
}

function fileProblem(file: unknown): string | null {
  if (!isRecord(file)) return "is not a description of a file";
  if (typeof file.file_path !== "string" || file.file_path === "") return "has no path";
  if (typeof file.file_size !== "number" || !Number.isInteger(file.file_size) || file.file_size < 0) {
    return "has no size in bytes";
  }
  if (typeof file.file_sha256 !== "string") return "has no digest";
  if (!IDENTIFICATION_METHODS.includes(file.file_identified_by as never)) {
    return "does not say how its format was identified";
  }
  if (file.file_media_type !== undefined && typeof file.file_media_type !== "string") {
    return "has a media type that is not text";
  }
  if (file.file_pronom_ids !== undefined && !isStringList(file.file_pronom_ids)) {
    return "has PRONOM identifiers that are not a list";
  }
  const fields = file.file_fields;
  if (fields !== undefined) {
    if (!Array.isArray(fields) || !fields.every((f) => isRecord(f) && typeof f.name === "string")) {
      return "has table fields without names";
    }
  }
  return null;
}
