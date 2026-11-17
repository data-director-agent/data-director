// dependency-cruiser passes silently when it is misconfigured, so these tests plant an import
// cycle and check that the package's own rules report it (.dependency-cruiser.cjs, #1059).
// @vitest-environment node
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { cruise, type ICruiseResult, type IForbiddenRuleType } from "dependency-cruiser";

const config = createRequire(import.meta.url)("../.dependency-cruiser.cjs") as {
  forbidden: IForbiddenRuleType[];
};

async function violations(files: Record<string, string>): Promise<string[]> {
  const dir = mkdtempSync(join(tmpdir(), "depcruise-"));
  try {
    for (const [name, code] of Object.entries(files)) writeFileSync(join(dir, name), code);
    const { output } = await cruise([dir], {
      validate: true,
      ruleSet: { forbidden: config.forbidden },
    });
    return (output as ICruiseResult).summary.violations.map((v) => v.rule.name);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}

describe("dependency rules", () => {
  it("reports an import cycle", async () => {
    const found = await violations({
      "a.js": 'import { b } from "./b.js";\nexport const a = () => b;\n',
      "b.js": 'import { a } from "./a.js";\nexport const b = () => a;\n',
    });
    expect(found).toContain("no-circular");
  });

  it("allows imports in one direction", async () => {
    const found = await violations({
      "a.js": 'import { b } from "./b.js";\nexport const a = () => b;\n',
      "b.js": "export const b = 1;\n",
    });
    expect(found).toEqual([]);
  });
});
