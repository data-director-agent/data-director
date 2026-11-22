import { FORMER_TABS, projectTabOf } from "./route";

describe("projectTabOf", () => {
  it("names a tab, and sends a merged tab's old path to the tab it joined", () => {
    expect(projectTabOf("people")).toBe("people");
    for (const [old, tab] of Object.entries(FORMER_TABS)) expect(projectTabOf(old)).toBe(tab);
    expect(projectTabOf("researchers")).toBe("people");
    expect(projectTabOf("members")).toBe("people");
  });

  it("names no tab for another path", () => {
    expect(projectTabOf("toString")).toBeNull();
    expect(projectTabOf("nothing")).toBeNull();
  });
});
