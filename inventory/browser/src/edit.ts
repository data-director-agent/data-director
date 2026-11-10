/**
 * Editing an inventory before it is added to a project, or revising the one a project holds
 * (docs/specs/projects.md). An edit is data: an `InventoryEdits` value says what the researcher
 * left out and what they stated, `edit` makes the next value from an action, and `applyEdits`
 * writes the value into the document. The document the editor started from is never changed, so
 * undoing is going back to an earlier value.
 *
 * What the inventory command found is never edited: a file's path, size, digest and PRONOM
 * matches, and a table's field names and types. The researcher states things beside those facts:
 * what a file or column is, what part a file plays, and which format a file is where the command
 * could not tell. A format the researcher chose says so (`file_identified_by: "researcher"`).
 */

import { countOmitted, describeOmitted, isOmitted, omit, type Omission } from "./omit";
import { FILE_ROLES, type FileInventory, type FileRole, type InventoryFile, type TableField } from "./types";

/** A format the researcher chose: one of the file's PRONOM matches, a media type, or both. */
export interface FormatStatement {
  pronomId?: string;
  mediaType?: string;
}

/**
 * What the researcher stated about one file. A key that is present changes the document: an
 * empty description or a null role clears what the document held.
 */
export interface FileStatement {
  description?: string;
  role?: FileRole | null;
  format?: FormatStatement;
}

/** Everything a researcher changed, keyed by file path and, for columns, by column name. */
export interface InventoryEdits {
  omitted: Omission;
  files: ReadonlyMap<string, FileStatement>;
  /** Column descriptions by table path, then column name; an empty description clears one. */
  fields: ReadonlyMap<string, ReadonlyMap<string, string>>;
}

/** No change at all. */
export const NO_EDITS: InventoryEdits = {
  omitted: { paths: new Set(), columns: new Map() },
  files: new Map(),
  fields: new Map(),
};

/** One change a researcher asks for. */
export type EditAction =
  | { kind: "omit" | "include"; path: string }
  | { kind: "omit-column" | "include-column"; path: string; column: string }
  | { kind: "describe"; path: string; text: string }
  | { kind: "role"; paths: readonly string[]; role: FileRole | null }
  | { kind: "format"; path: string; format: FormatStatement | null }
  | { kind: "describe-column"; path: string; column: string; text: string };

/** The longest description a researcher may give a file or a column, in characters. */
export const DESCRIPTION_LIMIT = 2000;

const MEDIA_TYPE = /^[a-z]+\/[a-z0-9][a-z0-9!#$&^_.+-]*$/i;

/**
 * Whether the researcher may choose `file`'s format: when the command matched several formats,
 * only guessed from the name, or matched none. A format recognised from the content is a fact.
 */
export function canChooseFormat(file: InventoryFile): boolean {
  return (
    (file.file_pronom_ids?.length ?? 0) > 1 ||
    file.file_identified_by === "extension" ||
    file.file_identified_by === "none" ||
    file.file_identified_by === "researcher"
  );
}

/**
 * Whether `format` may be stated for `file`: the file's format can be chosen, and the statement
 * names one of the file's own PRONOM matches, a well-formed media type, or both.
 */
export function isValidFormat(file: InventoryFile, format: FormatStatement): boolean {
  if (!canChooseFormat(file)) return false;
  const { pronomId, mediaType } = format;
  if (pronomId === undefined && mediaType === undefined) return false;
  if (pronomId !== undefined && !(file.file_pronom_ids ?? []).includes(pronomId)) return false;
  return mediaType === undefined || MEDIA_TYPE.test(mediaType);
}

function clean(text: string): string {
  return text.trim().slice(0, DESCRIPTION_LIMIT);
}

function toggled<T>(set: ReadonlySet<T>, item: T, present: boolean): ReadonlySet<T> {
  if (set.has(item) === present) return set;
  const next = new Set(set);
  if (present) next.add(item);
  else next.delete(item);
  return next;
}

function withEntry<K, V>(map: ReadonlyMap<K, V>, key: K, value: V | undefined): ReadonlyMap<K, V> {
  const next = new Map(map);
  if (value === undefined) next.delete(key);
  else next.set(key, value);
  return next;
}

/** `statement` with `key` set to `value`, or removed when `value` is undefined; undefined when empty. */
function restated<K extends keyof FileStatement>(
  statement: FileStatement | undefined,
  key: K,
  value: FileStatement[K] | undefined,
): FileStatement | undefined {
  const entries = Object.entries({ ...statement, [key]: value }).filter(([, v]) => v !== undefined);
  return entries.length ? (Object.fromEntries(entries) as FileStatement) : undefined;
}

function sameFormat(a: FormatStatement | undefined, b: FormatStatement | undefined): boolean {
  return a?.pronomId === b?.pronomId && a?.mediaType === b?.mediaType;
}

/**
 * The edits after `action`, made against `base`, the document the editor started from. An action
 * that would state what `base` already says removes the statement instead, so the edits hold only
 * real changes; an action `base` cannot take (an unknown path, or a format the file's matches do
 * not allow) returns `edits` as they are.
 */
export function edit(base: FileInventory, edits: InventoryEdits, action: EditAction): InventoryEdits {
  const byPath = new Map((base.inventory_files ?? []).map((file) => [file.file_path, file]));
  switch (action.kind) {
    case "omit":
    case "include": {
      const paths = toggled(edits.omitted.paths, action.path, action.kind === "omit");
      return paths === edits.omitted.paths ? edits : { ...edits, omitted: { ...edits.omitted, paths } };
    }
    case "omit-column":
    case "include-column": {
      const before = edits.omitted.columns.get(action.path) ?? new Set<string>();
      const after = toggled(before, action.column, action.kind === "omit-column");
      if (after === before) return edits;
      const columns = withEntry(edits.omitted.columns, action.path, after.size ? after : undefined);
      return { ...edits, omitted: { ...edits.omitted, columns } };
    }
    case "describe": {
      const file = byPath.get(action.path);
      if (!file) return edits;
      const text = clean(action.text);
      const value = text === (file.file_description ?? "") ? undefined : text;
      const statement = restated(edits.files.get(action.path), "description", value);
      return { ...edits, files: withEntry(edits.files, action.path, statement) };
    }
    case "role": {
      if (action.role !== null && !FILE_ROLES.includes(action.role)) return edits;
      let files = edits.files;
      for (const path of action.paths) {
        const file = byPath.get(path);
        if (!file) continue;
        const value = action.role === (file.file_role ?? null) ? undefined : action.role;
        files = withEntry(files, path, restated(files.get(path), "role", value));
      }
      return files === edits.files ? edits : { ...edits, files };
    }
    case "format": {
      const file = byPath.get(action.path);
      if (!file) return edits;
      let value: FormatStatement | undefined;
      if (action.format) {
        const format: FormatStatement = {
          ...(action.format.pronomId ? { pronomId: action.format.pronomId } : {}),
          ...(action.format.mediaType?.trim() ? { mediaType: action.format.mediaType.trim() } : {}),
        };
        if (!isValidFormat(file, format)) return edits;
        value = format;
      }
      if (sameFormat(value, edits.files.get(action.path)?.format)) return edits;
      const statement = restated(edits.files.get(action.path), "format", value);
      return { ...edits, files: withEntry(edits.files, action.path, statement) };
    }
    case "describe-column": {
      const field = byPath.get(action.path)?.file_fields?.find((f) => f.name === action.column);
      if (!field) return edits;
      const text = clean(action.text);
      const value = text === (field.field_description ?? "") ? undefined : text;
      const columns = withEntry(
        edits.fields.get(action.path) ?? new Map<string, string>(),
        action.column,
        value,
      );
      return { ...edits, fields: withEntry(edits.fields, action.path, columns.size ? columns : undefined) };
    }
  }
}

function describedFields(fields: TableField[], descriptions: ReadonlyMap<string, string>): TableField[] {
  return fields.map((field) => {
    const text = descriptions.get(field.name);
    if (text === undefined) return field;
    if (text) return { ...field, field_description: text };
    const rest = { ...field };
    delete rest.field_description;
    return rest;
  });
}

function stated(file: InventoryFile, statement: FileStatement | undefined): InventoryFile {
  if (!statement) return file;
  const next: InventoryFile = { ...file };
  if (statement.description !== undefined) {
    if (statement.description) next.file_description = statement.description;
    else delete next.file_description;
  }
  if (statement.role !== undefined) {
    if (statement.role) next.file_role = statement.role;
    else delete next.file_role;
  }
  if (statement.format) {
    const { pronomId, mediaType } = statement.format;
    if (pronomId) next.file_pronom_ids = [pronomId];
    if (mediaType) next.file_media_type = mediaType;
    next.file_identified_by = "researcher";
  }
  return next;
}

/**
 * `base` with `edits` written in: what was left out is removed, with one limitation counting it
 * and naming none of it (`omit`), and each statement is written beside the facts. With no edits,
 * `base` itself is returned.
 */
export function applyEdits(base: FileInventory, edits: InventoryEdits): FileInventory {
  const trimmed = omit(base, edits.omitted);
  if (!edits.files.size && !edits.fields.size) return trimmed;
  const files = (trimmed.inventory_files ?? []).map((file) => {
    const descriptions = edits.fields.get(file.file_path);
    const next = stated(file, edits.files.get(file.file_path));
    return descriptions && next.file_fields
      ? { ...next, file_fields: describedFields(next.file_fields, descriptions) }
      : next;
  });
  return { ...trimmed, inventory_files: files };
}

/** How much `edits` change `base`, counting only what is not also left out. */
export interface EditCounts {
  omittedFiles: number;
  omittedColumns: number;
  descriptions: number;
  roles: number;
  formats: number;
}

/** How much `edits` change `base`. */
export function countEdits(base: FileInventory, edits: InventoryEdits): EditCounts {
  const omitted = countOmitted(base, edits.omitted);
  const counts: EditCounts = {
    omittedFiles: omitted.files,
    omittedColumns: omitted.columns,
    descriptions: 0,
    roles: 0,
    formats: 0,
  };
  for (const file of base.inventory_files ?? []) {
    if (isOmitted(file.file_path, edits.omitted.paths)) continue;
    const statement = edits.files.get(file.file_path);
    if (statement?.description !== undefined) counts.descriptions += 1;
    if (statement?.role !== undefined) counts.roles += 1;
    if (statement?.format) counts.formats += 1;
    const dropped = edits.omitted.columns.get(file.file_path);
    for (const column of edits.fields.get(file.file_path)?.keys() ?? []) {
      if (!dropped?.has(column)) counts.descriptions += 1;
    }
  }
  return counts;
}

function plural(count: number, one: string, many: string): string {
  return `${count} ${count === 1 ? one : many}`;
}

/** "3 files and 1 column left out; 2 descriptions; 1 format chosen", or null when nothing changes. */
export function describeEdits(counts: EditCounts): string | null {
  const parts: string[] = [];
  const leftOut = describeOmitted({ files: counts.omittedFiles, columns: counts.omittedColumns });
  if (leftOut) parts.push(`${leftOut} left out`);
  if (counts.descriptions) parts.push(plural(counts.descriptions, "description", "descriptions"));
  if (counts.roles) parts.push(plural(counts.roles, "role", "roles"));
  if (counts.formats) parts.push(`${plural(counts.formats, "format", "formats")} chosen`);
  return parts.length ? parts.join("; ") : null;
}

/** How one inventory's files differ from another's, by path and then by digest. */
export interface InventoryDiff {
  added: string[];
  removed: string[];
  changed: string[];
  unchanged: number;
}

/** What is new, gone or changed in `after` compared with `before`; paths are sorted. */
export function diffInventories(before: FileInventory, after: FileInventory): InventoryDiff {
  const earlier = new Map((before.inventory_files ?? []).map((f) => [f.file_path, f.file_sha256]));
  const diff: InventoryDiff = { added: [], removed: [], changed: [], unchanged: 0 };
  const seen = new Set<string>();
  for (const file of after.inventory_files ?? []) {
    seen.add(file.file_path);
    const digest = earlier.get(file.file_path);
    if (digest === undefined) diff.added.push(file.file_path);
    else if (digest !== file.file_sha256) diff.changed.push(file.file_path);
    else diff.unchanged += 1;
  }
  for (const path of earlier.keys()) if (!seen.has(path)) diff.removed.push(path);
  for (const list of [diff.added, diff.removed, diff.changed]) list.sort();
  return diff;
}

/** Whether the researcher stated anything about `file` in the document. */
function hasStatements(file: InventoryFile): boolean {
  return (
    file.file_description !== undefined ||
    file.file_role !== undefined ||
    file.file_identified_by === "researcher" ||
    (file.file_fields ?? []).some((f) => f.field_description !== undefined)
  );
}

/**
 * What the researcher stated in `previous`, the inventory a project holds, as edits to `rescan`,
 * a new inventory of the same dataset, matched by path. A chosen format carries over only to a
 * file whose digest is unchanged; a description of a column only to a column of the same name.
 * Files with statements that `rescan` no longer lists are `orphaned`.
 *
 * What was left out of `previous` cannot carry over: it was never kept, by design, so a file
 * left out before is listed again in `rescan` and must be left out again.
 */
export function carryOver(
  previous: FileInventory,
  rescan: FileInventory,
): { edits: InventoryEdits; orphaned: string[] } {
  const now = new Map((rescan.inventory_files ?? []).map((file) => [file.file_path, file]));
  let edits = NO_EDITS;
  const orphaned: string[] = [];
  for (const file of previous.inventory_files ?? []) {
    if (!hasStatements(file)) continue;
    const current = now.get(file.file_path);
    if (!current) {
      orphaned.push(file.file_path);
      continue;
    }
    const path = file.file_path;
    if (file.file_description !== undefined) {
      edits = edit(rescan, edits, { kind: "describe", path, text: file.file_description });
    }
    if (file.file_role !== undefined) {
      edits = edit(rescan, edits, { kind: "role", paths: [path], role: file.file_role });
    }
    if (file.file_identified_by === "researcher" && file.file_sha256 === current.file_sha256) {
      const pronomId = file.file_pronom_ids?.length === 1 ? file.file_pronom_ids[0] : undefined;
      const format: FormatStatement = {
        ...(pronomId && current.file_pronom_ids?.includes(pronomId) ? { pronomId } : {}),
        ...(file.file_media_type ? { mediaType: file.file_media_type } : {}),
      };
      edits = edit(rescan, edits, { kind: "format", path, format });
    }
    for (const field of file.file_fields ?? []) {
      if (field.field_description === undefined) continue;
      edits = edit(rescan, edits, {
        kind: "describe-column",
        path,
        column: field.name,
        text: field.field_description,
      });
    }
  }
  return { edits, orphaned: orphaned.sort() };
}
