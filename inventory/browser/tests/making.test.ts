import { MAKING_AN_INVENTORY, systemFromPlatform } from "../src";

describe("MAKING_AN_INVENTORY", () => {
  it("covers Windows, macOS and Linux, each with both commands", () => {
    expect(MAKING_AN_INVENTORY.systems.map((s) => s.id)).toEqual(["windows", "macos", "linux"]);
    for (const system of MAKING_AN_INVENTORY.systems) {
      expect(system.install).toContain("astral.sh/uv/install");
      expect(system.run).toMatch(/^uvx data-director-inventory \S+ -o inventory\.json$/);
      expect(system.terminal).toMatch(/\.$/);
    }
  });

  it("says in one sentence that the data stay on the researcher's computer", () => {
    expect(MAKING_AN_INVENTORY.summary).toContain("never leave");
    expect(MAKING_AN_INVENTORY.summary.split(/[.!?]\s/)).toHaveLength(1);
  });
});

describe("systemFromPlatform", () => {
  it.each([
    ["Win32", "windows"],
    ["Windows", "windows"],
    ["MacIntel", "macos"],
    ["macOS", "macos"],
    ["Linux x86_64", "linux"],
    ["Linux", "linux"],
    ["Linux armv8l; Android", null],
    ["iPhone", null],
    ["", null],
    [undefined, null],
  ])("reads %s as %s", (platform, expected) => {
    expect(systemFromPlatform(platform)).toBe(expected);
  });
});
