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

// The function-size rules (eslint.config.js): a planted function over the limit is reported, so
// a misplaced `files` or `ignores` pattern cannot switch them off unnoticed.
describe("function size rules", () => {
  async function ruleIds(filePath: string, code: string): Promise<string[]> {
    const [result] = await eslint.lintText(code, { filePath });
    return (result?.messages ?? []).map((m) => m.ruleId ?? "");
  }

  const branches = (count: number) =>
    Array.from({ length: count }, (_, i) => `  if (n === ${i}) return ${i};`).join("\n");

  it("reports a function more complex than the limit", async () => {
    const code = `export function planted(n: number): number {\n${branches(20)}\n  return -1;\n}\n`;
    expect(await ruleIds("src/run/planted.ts", code)).toContain("complexity");
  });

  it("allows a function within the limit", async () => {
    const code = `export function planted(n: number): number {\n${branches(19)}\n  return -1;\n}\n`;
    expect(await ruleIds("src/run/planted.ts", code)).not.toContain("complexity");
  });

  it("reports blocks nested deeper than the limit", async () => {
    const code =
      "export function planted(a: boolean): number {\n" +
      "  if (a) { if (a) { if (a) { if (a) { if (a) { return 1; } } } } }\n  return 0;\n}\n";
    expect(await ruleIds("src/run/planted.ts", code)).toContain("max-depth");
  });
});

// Live regions (#948): only the announcer sets `aria-live`, so run progress is said in the frame's
// two regions and nowhere else.
describe("live region rule", () => {
  async function restricted(filePath: string, code: string): Promise<string[]> {
    const [result] = await eslint.lintText(code, { filePath });
    return (result?.messages ?? [])
      .filter((m) => m.ruleId === "no-restricted-syntax")
      .map((m) => m.message);
  }

  const region = 'export const x = <div aria-live="polite">Step started.</div>;\n';

  it("reports a component that sets aria-live itself", async () => {
    const messages = await restricted("src/components/run/Planted.tsx", region);
    expect(messages).toHaveLength(1);
    expect(messages[0]).toContain("useAnnounce");
  });

  it("allows the announcer to set it", async () => {
    expect(await restricted("src/components/ui/Announcer.tsx", region)).toEqual([]);
  });

  it("still reports a bare button in the announcer", async () => {
    const button = "export const x = <button>Go</button>;\n";
    expect(await restricted("src/components/ui/Announcer.tsx", button)).toHaveLength(1);
  });
});
