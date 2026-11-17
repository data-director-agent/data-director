import { afterEach, describe, expect, it, vi } from "vitest";

import { NoAnswer, Unreachable, httpConversationApi } from "./api";

function answering(status: number) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(new Response("<html>Bad Gateway</html>", { status })),
  );
}

const send = () => httpConversationApi.sendTurn("c1", "orchestrator", "hi", null);

describe("sending a turn", () => {
  afterEach(() => vi.unstubAllGlobals());

  it.each([502, 503, 504])("treats a %i from a proxy as no answer", async (status) => {
    answering(status);
    const sent = send();
    await expect(sent).rejects.toBeInstanceOf(NoAnswer);
    await expect(sent).rejects.toBeInstanceOf(Unreachable);
    await expect(sent).rejects.toMatchObject({ status });
  });

  it("reports any other server error as it is", async () => {
    answering(500);
    const sent = send();
    await expect(sent).rejects.not.toBeInstanceOf(Unreachable);
    await expect(sent).rejects.toThrow("the server answered 500");
  });
});
