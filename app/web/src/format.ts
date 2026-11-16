/**
 * Dates, times and numbers as the person's preferences say (`preferences.ts`): in the browser's
 * language or a chosen one, and with the 12- or 24-hour clock. Every date, time and number the
 * app shows to a person is written through these, never with `toLocaleString` directly.
 */

import { currentPreferences } from "./preferences";

function localeAndOptions<T extends Intl.DateTimeFormatOptions | Intl.NumberFormatOptions>(
  options: T,
  clock: boolean,
): [string | undefined, T] {
  const { dateLocale, hourCycle } = currentPreferences();
  const locale = dateLocale === "browser" ? undefined : dateLocale;
  if (!clock || hourCycle === "locale") return [locale, options];
  return [locale, { ...options, hourCycle }];
}

function valid(date: Date | string | number): Date | null {
  const d = date instanceof Date ? date : new Date(date);
  return Number.isNaN(d.getTime()) ? null : d;
}

/** A date and time, by default in full with seconds, as `toLocaleString()` writes it. */
export function formatDateTime(
  date: Date | string | number,
  options: Intl.DateTimeFormatOptions = {},
): string {
  const d = valid(date);
  if (!d) return String(date);
  return d.toLocaleString(...localeAndOptions(options, true));
}

/** A date alone. */
export function formatDate(
  date: Date | string | number,
  options: Intl.DateTimeFormatOptions = { dateStyle: "medium" },
): string {
  const d = valid(date);
  if (!d) return String(date);
  return d.toLocaleDateString(...localeAndOptions(options, false));
}

/** A time of day alone. */
export function formatTime(
  date: Date | string | number,
  options: Intl.DateTimeFormatOptions = { hour: "2-digit", minute: "2-digit" },
): string {
  const d = valid(date);
  if (!d) return String(date);
  return d.toLocaleTimeString(...localeAndOptions(options, true));
}

/** A number, grouped and with a decimal sign as the chosen language writes them. */
export function formatNumber(value: number, options: Intl.NumberFormatOptions = {}): string {
  const [locale, opts] = localeAndOptions(options, false);
  return new Intl.NumberFormat(locale, opts).format(value);
}
