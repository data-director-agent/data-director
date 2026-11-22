/**
 * The files a person should look at before deposit, judged from an inventory's names, sizes and
 * digests alone (#449). An inventory never holds contents, so a hint is a prompt for a person,
 * never a finding: a file with none may still hold personal data, sensitive locations or someone
 * else's material (docs/specs/personal-data.md).
 *
 * The rules are a copy of `dd_sdk.inventory_hints` (`sdk/src/dd_sdk/inventory_hints.py`), which
 * the File Archivist and the harness's deposit check read, so that the app marks the files they
 * list; this package may import neither, so change both together.
 */

import type { FileInventory, InventoryFile } from "./types";

/** What a file's names, size or digest suggest a person should check. */
export type HintKind =
  | "free_text"
  | "coordinates"
  | "third_party"
  | "governance"
  | "system_file"
  | "credentials"
  | "empty"
  | "duplicate";

/** One reason to look at one file. */
export interface FileHint {
  kind: HintKind;
  /** The word of a folder, file or field name, or the file name, that called for it. */
  matched?: string;
  /** What a person should check. */
  question: string;
  /** For a duplicate, the other files with the same digest. */
  related?: string[];
}

type Where = "folders" | "file" | "fields";

interface Rule {
  kind: HintKind;
  question: string;
  within?: readonly Where[];
  words?: readonly string[];
  names?: readonly string[];
  prefixes?: readonly string[];
  /** Ends of a file name, such as an extension. */
  suffixes?: readonly string[];
}

/** In the order of `dd_sdk.inventory_hints.RULES`: the order a file's hints are given in. */
export const HINT_RULES: readonly Rule[] = [
  {
    kind: "free_text",
    within: ["folders", "file"],
    words: [
      "notes", "fieldnotes", "fieldnote", "diary", "diaries", "journal", "notebook", "logbook",
      "interview", "interviews", "transcript", "transcripts", "consent", "correspondence",
      "email", "emails", "letters", "minutes",
    ],
    question:
      "Its name suggests free text, which often holds names, telephone numbers, access codes or " +
      "instructions. Read it before it is shared, and decide whether to leave it out or share a " +
      "redacted copy.",
  },
  {
    kind: "coordinates",
    within: ["fields"],
    words: [
      "lat", "lon", "lng", "latitude", "longitude", "easting", "northing", "eastings",
      "northings", "gridref", "coord", "coords", "coordinates", "gps", "geom", "geometry",
      "location",
    ],
    question:
      "A field name suggests coordinates or a location. Precise locations may expose people, " +
      "private land or protected species: a person decides whether to publish, generalise or " +
      "withhold them.",
  },
  {
    kind: "third_party",
    within: ["folders"],
    words: [
      "reference", "references", "external", "thirdparty", "third", "vendor", "downloaded",
      "purchased", "licensed", "bought", "supplied",
    ],
    question:
      "It is in a folder whose name suggests material from someone else, which may come under " +
      "its own licence or terms. Check who holds the rights before it is included.",
  },
  {
    kind: "governance",
    within: ["folders", "file"],
    words: [
      "agreement", "agreements", "licence", "license", "licences", "licenses", "permission",
      "permissions", "contract", "contracts", "governance", "dpa", "dsa", "nda", "terms",
    ],
    question:
      "Its name suggests terms or an agreement. Check what it allows and whether it is still in " +
      "force before deposit.",
  },
  {
    kind: "system_file",
    names: ["thumbs.db", "desktop.ini", ".ds_store", "ehthumbs.db"],
    prefixes: ["~$", "._"],
    question:
      "Its name is that of a file an operating system or program makes for itself. It is rarely " +
      "part of a dataset: leave it out unless it is.",
  },
  {
    kind: "credentials",
    within: ["file"],
    words: [
      "config", "secret", "secrets", "credential", "credentials", "password", "passwords", "token",
      "tokens", "apikey",
    ],
    names: [
      ".env", ".netrc", ".pgpass", ".htpasswd", ".pypirc", ".npmrc", ".git-credentials", ".s3cfg",
      "id_rsa", "id_dsa", "id_ecdsa", "id_ed25519", "credentials", "credentials.json",
      "secrets.yaml", "secrets.yml", "secrets.json",
    ],
    suffixes: [".ini", ".cfg", ".conf", ".env", ".pem", ".key", ".p12", ".pfx", ".keystore", ".jks"],
    question:
      "Its name is that of a configuration or credentials file, which may hold passwords, keys " +
      "or tokens. Check whether it does, and if so leave it out of the deposit.",
  },
  { kind: "empty", question: "The file is empty. Leave it out, or find what it should hold." },
  {
    kind: "duplicate",
    question:
      "It has the same digest as another file, so the two are byte-for-byte copies. Keep one.",
  },
];

/** Each hint kind in words a researcher reads, for a short label. */
export const HINT_LABELS: Readonly<Record<HintKind, string>> = {
  free_text: "May hold free text",
  coordinates: "May hold locations",
  third_party: "May be someone else's",
  governance: "Terms or an agreement",
  system_file: "System file",
  credentials: "May hold credentials",
  empty: "Empty",
  duplicate: "Exact copy",
};

/** What is said wherever hints are shown, so that no hint is never read as clearance. */
export const HINT_LIMITATION =
  "Data Director sees names, not contents: a file not marked may still hold personal data, " +
  "sensitive locations or someone else's material.";

const WORD = /[a-z]+/g;

function wordsOf(...names: string[]): string[] {
  return names.flatMap((n) => n.toLowerCase().match(WORD) ?? []);
}

function hintFor(rule: Rule, file: InventoryFile, copies: Map<string, string[]>): FileHint | null {
  const { kind, question } = rule;
  if (kind === "empty") return file.file_size === 0 ? { kind, question } : null;
  if (kind === "duplicate") {
    const related = (copies.get(file.file_sha256) ?? []).filter((p) => p !== file.file_path);
    return related.length ? { kind, question, related } : null;
  }
  return namedHint(rule, file);
}

/** A hint whose file's name, or a word in its folders, name or fields, the rule names. */
function namedHint(rule: Rule, file: InventoryFile): FileHint | null {
  const { kind, question } = rule;
  const segments = file.file_path.split("/");
  const name = segments.at(-1) ?? file.file_path;
  const lower = name.toLowerCase();
  if (
    rule.names?.includes(lower) ||
    rule.prefixes?.some((p) => lower.startsWith(p)) ||
    rule.suffixes?.some((s) => lower.endsWith(s))
  ) {
    return { kind, question, matched: name };
  }
  const within = rule.within ?? [];
  const places = [
    ...(within.includes("folders") ? segments.slice(0, -1) : []),
    ...(within.includes("file") ? [name] : []),
    ...(within.includes("fields") ? (file.file_fields ?? []).map((f) => f.name) : []),
  ];
  const matched = wordsOf(...places).find((w) => rule.words?.includes(w));
  return matched ? { kind, question, matched } : null;
}

/** The hints for each file of `inventory` that has any, keyed by path, in the order of its files. */
export function fileHints(inventory: FileInventory): Map<string, FileHint[]> {
  const files = inventory.inventory_files ?? [];
  const copies = new Map<string, string[]>();
  for (const f of files) {
    if (f.file_size > 0 && f.file_sha256) {
      copies.set(f.file_sha256, [...(copies.get(f.file_sha256) ?? []), f.file_path]);
    }
  }
  const hints = new Map<string, FileHint[]>();
  for (const f of files) {
    const found = HINT_RULES.map((r) => hintFor(r, f, copies)).filter((h): h is FileHint => h !== null);
    if (found.length) hints.set(f.file_path, found);
  }
  return hints;
}
