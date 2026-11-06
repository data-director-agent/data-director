// eslint-plugin-boundaries does nothing, silently, when its import resolver is
// not configured. These tests plant violations and check that they are reported.
// The layers are described in docs/specs/app.md.
// @vitest-environment node
import { ESLint } from "eslint";

const eslint = new ESLint({ cwd: process.cwd() });

async function boundaryMessages(filePath: string, code: string): Promise<string[]> {
  const [result] = await eslint.lintText(code, { filePath });
  return (result?.messages ?? [])
    .filter((m) => m.ruleId === "boundaries/dependencies")
    .map((m) => m.message);
}

describe("layer rules", () => {
  it("reports the UI kit importing a feature component", async () => {
    const messages = await boundaryMessages(
      "src/components/ui/Planted.tsx",
      'import { Outcome } from "../run/Outcome";\nexport const x = Outcome;\n',
    );
    expect(messages).toHaveLength(1);
    expect(messages[0]).toContain("UI kit");
  });

  it("reports a domain folder importing a component", async () => {
    const messages = await boundaryMessages(
      "src/run/planted.ts",
      'import { Outcome } from "../components/run/Outcome";\nexport const x = Outcome;\n',
    );
    expect(messages).toHaveLength(1);
    expect(messages[0]).toContain("Domain");
  });

  it("allows a feature component to import the UI kit", async () => {
    const messages = await boundaryMessages(
      "src/components/run/Planted.tsx",
      'import { Button } from "../ui/Button";\nexport const x = Button;\n',
    );
    expect(messages).toEqual([]);
  });
});
