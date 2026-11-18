import { afterEach, describe, expect, it, vi } from "vitest";

import forbiddenFixture from "../../fixtures/project-facts-forbidden.json";
import { DecisionConflict } from "./api";
import { FactForbidden, cleaned, httpFactsApi, missingSlots } from "./facts";

const PROJECT = "01900000-0000-7000-8000-000000000001";
const CONFLICT = {
  type: "https://w3id.org/data-director/problems/proposal-not-found",
  title: "No such proposal",
  status: 404,
  detail: "This project holds no proposal.",
};

function answering(status: number, body: unknown) {
  const fetched = vi.fn(() => Promise.resolve(new Response(JSON.stringify(body), { status })));
  vi.stubGlobal("fetch", fetched);
  return fetched;
}

afterEach(() => vi.unstubAllGlobals());

describe("httpFactsApi", () => {
  it("posts a decision and names no one who decided", async () => {
    const fetched = answering(201, { proposals: [], decisions: [] });
    await httpFactsApi.decideFact(PROJECT, { verdict: "confirmed", proposal: "p" });
    const [url, init] = fetched.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe(`/api/projects/${PROJECT}/facts/decisions`);
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({ verdict: "confirmed", proposal: "p" });
  });

  it("raises a proposal that is not there, or has moved on, as a conflict", async () => {
    for (const status of [404, 409]) {
      answering(status, { ...CONFLICT, status });
      await expect(httpFactsApi.decideFact(PROJECT, { verdict: "confirmed", proposal: "p" })).rejects.toBeInstanceOf(
        DecisionConflict,
      );
    }
  });

  it("raises an owner's kind of fact refused to a member as FactForbidden", async () => {
    answering(403, forbiddenFixture);
    const error = await httpFactsApi
      .decideFact(PROJECT, { verdict: "confirmed", proposal: "p" })
      .catch((e: unknown) => e);
    expect(error).toBeInstanceOf(FactForbidden);
  });
});

describe("a fact the person gives", () => {
  it("is missing what its kind needs until it is filled in", () => {
    expect(missingSlots({ fact_kind: "licence", fact_subject: "licence" })).toEqual(["licence_id"]);
    expect(missingSlots({ fact_kind: "licence", fact_subject: "licence", licence_id: "CC0-1.0" })).toEqual([]);
  });

  it("is sent without empty values or the agent's reasons", () => {
    expect(
      cleaned({
        fact_kind: "funder",
        fact_subject: "NERC",
        fact_funder_name: "NERC",
        fact_funder_ror: " ",
        fact_required_by: [],
        proposed_because: "The proposal says so.",
      }),
    ).toEqual({ fact_kind: "funder", fact_subject: "NERC", fact_funder_name: "NERC" });
  });
});
