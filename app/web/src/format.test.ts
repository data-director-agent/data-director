import { formatDate, formatDateTime, formatNumber, formatTime } from "./format";
import { setPreference } from "./preferences";

const AFTERNOON = new Date(2026, 10, 16, 14, 5);

afterEach(() => localStorage.clear());

describe("format", () => {
  it("writes dates in the chosen style", () => {
    setPreference("dateLocale", "en-GB");
    expect(formatDate(AFTERNOON)).toBe(AFTERNOON.toLocaleDateString("en-GB", { dateStyle: "medium" }));
    setPreference("dateLocale", "en-US");
    expect(formatDate(AFTERNOON)).toBe(AFTERNOON.toLocaleDateString("en-US", { dateStyle: "medium" }));
  });

  it("follows the chosen clock", () => {
    setPreference("dateLocale", "en-GB");
    setPreference("hourCycle", "h12");
    expect(formatTime(AFTERNOON)).toMatch(/02:05\s?pm/i);
    setPreference("hourCycle", "h23");
    expect(formatTime(AFTERNOON)).toBe("14:05");
    expect(formatDateTime(AFTERNOON, { dateStyle: "medium", timeStyle: "short" })).toContain("14:05");
  });

  it("writes numbers in the chosen style", () => {
    setPreference("dateLocale", "en-GB");
    expect(formatNumber(1234.5)).toBe("1,234.5");
  });

  it("gives back what it was given when it is not a date", () => {
    expect(formatDateTime("not a date")).toBe("not a date");
    expect(formatDate("")).toBe("");
  });
});
