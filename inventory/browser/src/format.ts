/** An inventory's facts in words a researcher reads, in British English. */

import type { IdentificationMethod } from "./types";

/** Decimal units, as file managers on most systems show sizes. */
const UNITS = ["bytes", "kB", "MB", "GB", "TB", "PB"] as const;
const STEP = 1000;

const ONE_DECIMAL = new Intl.NumberFormat("en-GB", { maximumFractionDigits: 1 });
const WHOLE = new Intl.NumberFormat("en-GB", { maximumFractionDigits: 0 });

/** "1 byte", "999 bytes", "1.2 kB", "3.4 GB". */
export function formatBytes(bytes: number): string {
  if (bytes === 1) return "1 byte";
  let value = bytes;
  let unit = 0;
  while (value >= STEP && unit < UNITS.length - 1) {
    value /= STEP;
    unit += 1;
  }
  // Rounding 999.95 kB to one decimal would read "1,000 kB": step up instead.
  if (unit < UNITS.length - 1 && Number(value.toFixed(1)) >= STEP) {
    value /= STEP;
    unit += 1;
  }
  return `${(unit === 0 ? WHOLE : ONE_DECIMAL).format(value)} ${UNITS[unit]}`;
}

/** "1 file", "42 files". */
export function formatFileCount(count: number): string {
  return count === 1 ? "1 file" : `${WHOLE.format(count)} files`;
}

const DATE = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "short",
  year: "numeric",
  timeZone: "UTC",
});

/** "1 Nov 2026", or null when `iso` is not a date. */
export function formatDate(iso: string): string | null {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? null : DATE.format(date);
}

/** "42 files, made 1 Nov 2026". */
export function describeInventory(fileCount: number, madeAt: string): string {
  const files = formatFileCount(fileCount);
  const made = formatDate(madeAt);
  return made ? `${files}, made ${made}` : files;
}

const IDENTIFICATION: Record<IdentificationMethod, string> = {
  signature: "Recognised from its content",
  container: "Recognised from the files inside it",
  extension: "Guessed from its name",
  none: "Not recognised",
  researcher: "Chosen by the researcher",
};

/** How a file's format was identified, as a phrase: "Recognised from its content". */
export function identificationLabel(method: IdentificationMethod): string {
  return IDENTIFICATION[method];
}

/** A PRONOM identifier's page in the register. */
export function pronomUrl(puid: string): string {
  return `https://www.nationalarchives.gov.uk/PRONOM/${puid}`;
}
