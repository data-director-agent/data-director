import { FORMER_TABS, factsPath, projectTabOf } from "./route";

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

describe("factsPath", () => {
  it("goes to the facts tab, naming each fact given once, so a link lands on them", () => {
    expect(factsPath("p 1")).toBe("/projects/p%201/facts");
    const keys = ["file_inclusion:data/a (copy).csv", "sensitivity:sites.csv", "sensitivity:sites.csv"];
    const href = new URL(factsPath("p", keys), location.origin);
    expect(href.pathname).toBe("/projects/p/facts");
    expect(href.searchParams.getAll("fact")).toEqual([keys[0], keys[1]]);
  });
});
