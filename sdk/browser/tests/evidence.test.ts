import { describe, expect, it } from "vitest";

import { evidenceCredit } from "../src";

describe("evidenceCredit", () => {
  it("credits Open Policy Finder, with its licence, by the label of the copy that answered", () => {
    const credit = evidenceCredit({ snapshot_ref: "open-policy-finder:live:2026-11-25" });
    expect(credit?.text).toContain("Jisc Open Policy Finder");
    expect(credit?.text).toContain("CC BY-NC-ND 4.0");
    expect(credit?.href).toMatch(/^https:\/\//);
  });

  it("gives none for a source that asks for none", () => {
    expect(evidenceCredit({ snapshot_ref: "ror:dump:v2" })).toBeNull();
    expect(evidenceCredit({ snapshot_ref: null })).toBeNull();
    expect(evidenceCredit({})).toBeNull();
  });
});
