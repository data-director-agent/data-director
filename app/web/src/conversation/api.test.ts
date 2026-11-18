import { HttpAgent } from "@ag-ui/client";
import { describe, expect, it, vi } from "vitest";

import { RunRefused } from "../http";
import { streamRun } from "../run/transport";
import { SignedOut } from "../session/api";
import { NoAnswer, streamFailure, turnBody, TurnConflict, Unreachable } from "./api";

const PROBLEM = { type: "https://example.org/p", title: "Refused", detail: "Not this turn." };

/** Why a turn's stream could not be opened, when the server answers with `response`. */
async function refusal(response: () => Promise<Response>): Promise<Error> {
  const agent = new HttpAgent({ url: "/stream", threadId: "c1", fetch: response });
  const turn = { runId: "r1", forwardedProps: turnBody("o", "hi", null, null, null, null) };
  const error = await streamRun(agent, turn, () => undefined).done.then(
    () => null,
    (e: unknown) => e,
  );
  return streamFailure(error);
}

const answering = (status: number, body: unknown = "<html>Bad Gateway</html>") => () =>
  Promise.resolve(
    typeof body === "string"
      ? new Response(body, { status })
      : Response.json(body, { status }),
  );

describe("a turn refused before its stream opened", () => {
  it.each([502, 503, 504])("treats a %i from a proxy as no answer", async (status) => {
    const error = await refusal(answering(status));
    expect(error).toBeInstanceOf(NoAnswer);
    expect(error).toBeInstanceOf(Unreachable);
    expect(error).toMatchObject({ status });
  });

  it("treats no response at all as unreachable", async () => {
    const error = await refusal(() => Promise.reject(new TypeError("Failed to fetch")));
    expect(error).toBeInstanceOf(Unreachable);
    expect(error).not.toBeInstanceOf(NoAnswer);
  });

  it("raises a conflict, a refusal and a sign-out as the JSON route did", async () => {
    expect(await refusal(answering(409, PROBLEM))).toBeInstanceOf(TurnConflict);
    const refused = await refusal(answering(400, PROBLEM));
    expect(refused).toBeInstanceOf(RunRefused);
    expect((refused as RunRefused).problem).toEqual(PROBLEM);
    const signedOut = vi.fn();
    window.addEventListener("dd-signed-out", signedOut);
    expect(await refusal(answering(401, PROBLEM))).toBeInstanceOf(SignedOut);
    window.removeEventListener("dd-signed-out", signedOut);
    expect(signedOut).toHaveBeenCalled();
  });

  it("reports any other server error as it is", async () => {
    const error = await refusal(answering(500));
    expect(error).not.toBeInstanceOf(Unreachable);
    expect(error.message).toBe("the server answered 500");
  });

  it("passes on an error it has already been given as such", () => {
    const conflict = new TurnConflict(PROBLEM);
    expect(streamFailure(conflict)).toBe(conflict);
    expect(streamFailure(new NoAnswer(502))).toBeInstanceOf(NoAnswer);
  });
});

describe("a turn's body", () => {
  it("carries the answer, inventory and document only when there is one", () => {
    expect(turnBody("o", "hi", null, null, null, null)).toEqual({
      agent_id: "o",
      message_text: "hi",
      follows: null,
    });
    const document = { name: "a.md", media_type: "text/markdown", text: "# A", size: 3 };
    expect(turnBody("o", "hi", "t1", null, null, document)).toEqual({
      agent_id: "o",
      message_text: "hi",
      follows: "t1",
      documentation: { name: "a.md", media_type: "text/markdown", text: "# A" },
    });
  });

  it("carries a Word document or PDF as the file, never its text", () => {
    const pdf = { name: "p.pdf", media_type: "application/pdf", text: "Read", size: 4, data: "JVBE" };
    const sent = turnBody("o", "", null, null, null, pdf).documentation;
    expect(sent).toEqual({ name: "p.pdf", media_type: "application/pdf", data: "JVBE" });
  });
});
