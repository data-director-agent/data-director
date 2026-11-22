/**
 * The browser bundle's licence notices (`NOTICES.md`, written by `build.ts`). Serving the bundle
 * redistributes everything in it, so the notices name every component with its licence and where
 * its source is: Pyodide and every wheel in `MPL-2.0` say so (section 3.2), and the PRONOM
 * signatures the inventory package and fido carry need The National Archives' attribution statement (Open Government
 * Licence). Pure: the build reads each wheel's metadata and hands it in.
 */

import { BundleError } from "./resolve.ts";

/** Where the build writes the notices in the bundle. Not in `manifest.files`: no scan reads it. */
export const NOTICES = "NOTICES.md";

/** The attribution statement the Open Government Licence asks for, as the app shows it too. */
export const OGL_STATEMENT =
  "Contains public sector information licensed under the Open Government Licence v3.0.";
export const OGL_URL =
  "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/";

/** What a wheel's `*.dist-info/METADATA` says of its licence, and which licence files it carries. */
export interface WheelLicence {
  name: string;
  version: string;
  /** `License-Expression`, else a one-line `License`, else the `License ::` classifiers. */
  licence: string;
  /** The licence files in the wheel, by their path in it. */
  files: string[];
}

/** A `License` field longer than this, or over lines, is the licence's text, not its name. */
const NAME_LENGTH = 64;

/** The licence named in a wheel's core metadata (`METADATA`, an email-style header block). */
export function licenceOf(metadata: string): string | undefined {
  const headers = metadata.split(/\r?\n\r?\n/, 1)[0] ?? "";
  const fields = headers.split(/\r?\n(?![ \t])/).map((line) => {
    const colon = line.indexOf(":");
    return [line.slice(0, colon).toLowerCase(), line.slice(colon + 1).trim()] as const;
  });
  const field = (key: string) => fields.find(([k]) => k === key)?.[1];
  const expression = field("license-expression");
  if (expression) return expression;
  const named = field("license");
  if (named && !named.includes("\n") && named.length <= NAME_LENGTH) return named;
  const classifiers = fields
    .filter(([k, v]) => k === "classifier" && v.startsWith("License ::"))
    .map(([, v]) => v.split("::").at(-1)?.trim() ?? "");
  return classifiers.length ? classifiers.join(" or ") : undefined;
}

/** The licence of one wheel from its metadata and file list; a wheel naming none fails the build. */
export function wheelLicence(
  name: string,
  version: string,
  metadata: string,
  paths: string[],
): WheelLicence {
  const licence = licenceOf(metadata);
  if (!licence) throw new BundleError(`${name} ${version} names no licence in its metadata`);
  const files = paths.filter((p) => /^(licen[cs]e|copying|notice)/i.test(p.split("/").at(-1) ?? ""));
  return { name, version, licence, files };
}

export interface NoticesInput {
  pyodide: string;
  python: string;
  wheels: WheelLicence[];
  /** The PRONOM release the inventory package pins, such as `v125`. */
  pronom: string | undefined;
}

/** `NOTICES.md`: Pyodide, each wheel, and the PRONOM attribution. */
export function renderNotices({ pyodide, python, wheels, pronom }: NoticesInput): string {
  const rows = [...wheels]
    .sort((a, b) => a.name.toLowerCase().localeCompare(b.name.toLowerCase()))
    .map(
      (w) =>
        `| [${w.name}](https://pypi.org/project/${w.name}/${w.version}/) | ${w.version} | ${w.licence} | ${w.files.map((f) => `\`${f}\``).join(", ") || "none"} |`,
    );
  return [
    "# Licence notices for the inventory scanner",
    "",
    "The app serves these files so that your browser can describe a folder without sending its",
    "files anywhere. Each component keeps its own licence; none of them is changed.",
    "",
    "## Pyodide",
    "",
    `[Pyodide](https://pyodide.org/) ${pyodide} (\`pyodide.mjs\`, \`pyodide.asm.mjs\`,`,
    "`pyodide.asm.wasm`, `python_stdlib.zip`) is licensed under the Mozilla Public License 2.0.",
    `Its source is at <https://github.com/pyodide/pyodide/tree/${pyodide}>, with the licences of`,
    `the libraries it compiles in. It includes CPython ${python}, licensed under the PSF License`,
    `Agreement, whose source is at <https://github.com/python/cpython/tree/v${python}>.`,
    "",
    "## PRONOM signatures",
    "",
    `fido identifies formats with The National Archives' PRONOM signatures${pronom ? ` (${pronom})` : ""},`,
    "which the inventory package carries under `dd_inventory/pronom/`; fido's wheel carries an",
    "older release under `fido/conf/`.",
    "",
    `${OGL_STATEMENT} <${OGL_URL}>`,
    "",
    "## Python packages",
    "",
    "Each wheel in `wheels/` is served as published, with its licence text in the files named.",
    "Its source is on its PyPI page.",
    "",
    "| Package | Version | Licence | Licence files in the wheel |",
    "| --- | --- | --- | --- |",
    ...rows,
    "",
  ].join("\n");
}
