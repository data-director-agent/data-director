import { describe, expect, it, vi } from "vitest";

import { RunRefused, json } from "./http";
import { SIGNED_OUT, SignedOut } from "./session/api";

const PROBLEM = { type: "about:blank", title: "Refused", status: 400, detail: "not allowed" };

function respond(status: number, body: unknown): Response {
  return new Response(typeof body === "string" ? body : JSON.stringify(body), { status });
}

describe("json", () => {
  it("reads the body of a successful response", async () => {
    await expect(json<{ a: number }>(respond(200, { a: 1 }))).resolves.toEqual({ a: 1 });
  });

  it("raises SignedOut, and tells the page, for a 401", async () => {
    const heard = vi.fn();
    window.addEventListener(SIGNED_OUT, heard);
    await expect(json(respond(401, PROBLEM))).rejects.toBeInstanceOf(SignedOut);
    window.removeEventListener(SIGNED_OUT, heard);
    expect(heard).toHaveBeenCalledOnce();
  });

  it("raises RunRefused with the Problem Details of a 400", async () => {
    const error = await json(respond(400, PROBLEM)).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(RunRefused);
    expect((error as RunRefused).problem).toEqual(PROBLEM);
  });

  it("raises a plain error when the error body is not Problem Details", async () => {
    const error = await json(respond(400, "<html>")).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(Error);
    expect(error).not.toBeInstanceOf(RunRefused);
  });

  it("raises a plain error for another status", async () => {
    const error = await json(respond(500, PROBLEM)).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(Error);
    expect(error).not.toBeInstanceOf(RunRefused);
  });

  it("raises what the endpoint makes of a status before the common errors", async () => {
    class Conflict extends Error {}
    const refine = vi.fn((status: number) => (status === 400 ? new Conflict() : null));
    await expect(json(respond(400, PROBLEM), refine)).rejects.toBeInstanceOf(Conflict);
    expect(refine).toHaveBeenCalledWith(400, PROBLEM);
  });

  it("falls back on the common errors when the endpoint makes nothing of a status", async () => {
    await expect(json(respond(400, PROBLEM), () => null)).rejects.toBeInstanceOf(RunRefused);
  });
});
