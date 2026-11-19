/**
 * An inventory of several folders (docs/specs/projects.md). A project holds one inventory, which
 * may be made of parts: each part is one scan of one folder, mounted at a folder name, and every
 * file's path begins with its part's folder. A researcher updates a folder by scanning it again,
 * which replaces that part whole, or adds a folder the inventory does not have; the other parts
 * stay as they were. A part is never merged file by file, since a scan cannot tell a file that is
 * gone from one that was not scanned.
 *
 * Everything here makes a new document; none changes the one it is given. What the researcher
 * stated about the files is in the documents themselves, so `carryOver` from the inventory a
 * project holds (or from `asParts` of it) onto `withPart`'s result carries it by path.
 */

import type { FileInventory, InventoryFile, InventoryPart, PersonalDataFinding } from "./types";

/** A folder name that cannot be a part's folder; the message is a sentence a researcher can read. */
export class NotAPartFolder extends Error {
  override name = "NotAPartFolder";
}

/** Why `folder` cannot name a part, or null when it can. */
export function partFolderProblem(folder: string): string | null {
  if (folder.trim() === "") return "Give the folder a name.";
  if (folder.startsWith("/") || folder.endsWith("/")) {
    return "A folder name does not begin or end with a slash.";
  }
  const segments = folder.split("/");
  if (segments.some((s) => s === "")) return "A folder name has nothing between two slashes.";
  if (segments.some((s) => s === "." || s === "..")) return "A folder name has no . or .. in it.";
  return null;
}

function within(path: string, folder: string): boolean {
  return path === folder || path.startsWith(`${folder}/`);
}

/** The prefix a part's limitations take in `inventory_limitations`. */
function lead(folder: string): string {
  return `In ${folder}: `;
}

/**
 * What is wrong with `inventory`'s parts, as the store would say it: a bad folder name, folders
 * that overlap, or a file under no part's folder. Empty for an inventory without parts.
 */
export function partProblems(inventory: FileInventory): string[] {
  const parts = inventory.inventory_parts;
  if (!parts?.length) return [];
  const folders = parts.map((p) => p.part_folder);
  const problems: string[] = [];
  for (const folder of folders) {
    const problem = partFolderProblem(folder);
    if (problem) problems.push(`${folder}: ${problem}`);
  }
  folders.forEach((a, i) => {
    for (const b of folders.slice(i + 1)) {
      if (within(a, b) || within(b, a)) problems.push(`The folders ${a} and ${b} overlap.`);
    }
  });
  for (const file of inventory.inventory_files ?? []) {
    if (!folders.some((f) => file.file_path.startsWith(`${f}/`))) {
      problems.push(`${file.file_path} is in none of the inventory's folders.`);
    }
  }
  return problems;
}

/** The inventory's parts, or null for an inventory of one folder without parts. */
export function partsOf(inventory: FileInventory): readonly InventoryPart[] | null {
  return inventory.inventory_parts?.length ? inventory.inventory_parts : null;
}

/** The part whose folder `path` lies in, if any. */
export function partOf(inventory: FileInventory, path: string): InventoryPart | undefined {
  return inventory.inventory_parts?.find((p) => path.startsWith(`${p.part_folder}/`));
}

/** The limitations of `inventory` that concern no one part. */
function generalLimitations(inventory: FileInventory): string[] {
  const leads = (inventory.inventory_parts ?? []).map((p) => lead(p.part_folder));
  return (inventory.inventory_limitations ?? []).filter((s) => !leads.some((l) => s.startsWith(l)));
}

/**
 * `files` and `parts` as one inventory: files sorted by path, the top-level tool, version and
 * date those of the latest part, the limitations the general ones then each part's, and the
 * personal-data findings every part's, or absent when any part's are, as no detector ran there.
 */
export function assemble(
  base: FileInventory,
  files: readonly InventoryFile[],
  parts: readonly InventoryPart[],
  general: readonly string[],
): FileInventory {
  const sorted = [...parts].sort((a, b) => (a.part_folder < b.part_folder ? -1 : 1));
  const latest = sorted.reduce<InventoryPart | undefined>(
    (best, p) => (!best || Date.parse(p.part_made_at) > Date.parse(best.part_made_at) ? p : best),
    undefined,
  );
  const limitations = [
    ...general,
    ...sorted.flatMap((p) => (p.part_limitations ?? []).map((s) => lead(p.part_folder) + s)),
  ];
  const document: FileInventory = {
    ...base,
    inventory_files: [...files].sort((a, b) => (a.file_path < b.file_path ? -1 : 1)),
    inventory_parts: sorted,
    inventory_limitations: limitations,
  };
  delete document.inventory_identified_with;
  if (latest) {
    document.inventory_tool = latest.part_tool;
    document.inventory_tool_version = latest.part_tool_version;
    document.inventory_made_at = latest.part_made_at;
    if (latest.part_identified_with) document.inventory_identified_with = latest.part_identified_with;
  }
  if (!limitations.length) delete document.inventory_limitations;
  if (!sorted.length) delete document.inventory_parts;
  else if (sorted.every((p) => p.part_personal_data)) {
    document.inventory_personal_data = sorted.flatMap((p) => p.part_personal_data ?? []);
  } else delete document.inventory_personal_data;
  return document;
}

/** `findings` with each path under `folder`, or absent when they are. */
function findingsUnder(
  findings: readonly PersonalDataFinding[] | undefined,
  folder: string,
): PersonalDataFinding[] | undefined {
  return findings?.map((f) => ({ ...f, finding_file: `${folder}/${f.finding_file}` }));
}

/** `scan`'s parts mounted at `folder`: one for a scan of one folder, or one for each of its own. */
function mount(scan: FileInventory, folder: string): { files: InventoryFile[]; parts: InventoryPart[] } {
  const files = (scan.inventory_files ?? []).map((f) => ({ ...f, file_path: `${folder}/${f.file_path}` }));
  const own = partsOf(scan);
  if (own) {
    const parts = own.map((p) => {
      const part: InventoryPart = { ...p, part_folder: `${folder}/${p.part_folder}` };
      const findings = findingsUnder(p.part_personal_data, folder);
      if (findings) part.part_personal_data = findings;
      return part;
    });
    return { files, parts };
  }
  const part: InventoryPart = {
    part_folder: folder,
    part_tool: scan.inventory_tool,
    part_tool_version: scan.inventory_tool_version,
    part_made_at: scan.inventory_made_at,
  };
  if (scan.inventory_identified_with) part.part_identified_with = scan.inventory_identified_with;
  if (scan.inventory_limitations?.length) part.part_limitations = [...scan.inventory_limitations];
  const findings = findingsUnder(scan.inventory_personal_data, folder);
  if (findings) part.part_personal_data = findings;
  return { files, parts: [part] };
}

/**
 * `inventory`, an inventory of one folder, as an inventory of one part mounted at `folder`: every
 * path begins with it, and what the researcher stated moves with the files. An inventory that
 * already has parts is returned as it is.
 */
export function asParts(inventory: FileInventory, folder: string): FileInventory {
  if (partsOf(inventory)) return inventory;
  const problem = partFolderProblem(folder);
  if (problem) throw new NotAPartFolder(problem);
  const { files, parts } = mount(inventory, folder);
  return assemble(inventory, files, parts, []);
}

/**
 * The inventory `stored` becomes when `scan`, a scan of one folder, is mounted at `folder`: the
 * part at `folder`, and any parts inside it, are replaced by the scan, and every other part is
 * kept as it was. A `folder` the inventory does not have adds a part. An inventory without parts
 * must first be named with `asParts`. Throws `NotAPartFolder` for a bad name, or a folder inside
 * one of `stored`'s parts, since a part is replaced whole and never in part.
 */
export function withPart(stored: FileInventory, scan: FileInventory, folder: string): FileInventory {
  const problem = partFolderProblem(folder);
  if (problem) throw new NotAPartFolder(problem);
  const parts = partsOf(stored);
  if (!parts) {
    throw new NotAPartFolder("Name the folder the inventory already has before adding another.");
  }
  const outer = parts.find((p) => p.part_folder !== folder && within(folder, p.part_folder));
  if (outer) {
    throw new NotAPartFolder(
      `${folder} is inside ${outer.part_folder}, which is scanned as a whole: scan ` +
        `${outer.part_folder} again instead.`,
    );
  }
  const kept = parts.filter((p) => !within(p.part_folder, folder));
  const files = (stored.inventory_files ?? []).filter((f) => !within(f.file_path, folder));
  const mounted = mount(scan, folder);
  return assemble(stored, [...files, ...mounted.files], [...kept, ...mounted.parts], generalLimitations(stored));
}
