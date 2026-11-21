import { describe, expect, it } from "vitest";

import { serverAnswered } from "./status";

describe("serverAnswered", () => {
  it.each([502, 503])("says the app is restarting on %i", (status) => {
    expect(serverAnswered(status)).toMatch(/restarting/);
    expect(serverAnswered(status)).toContain(String(status));
  });

  it("gives any other status as it is", () => {
    expect(serverAnswered(500)).not.toMatch(/restarting/);
    expect(serverAnswered(500)).toContain("500");
  });
});
