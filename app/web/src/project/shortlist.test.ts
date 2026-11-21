import { shortlistOf, unlistedOf } from "./shortlist";
import { ORDA, ZENODO, shortlistRun } from "../test/shortlist";

describe("shortlistOf", () => {
  it("names each candidate by the re3data record it rests on, in the advisor's order", () => {
    expect(shortlistOf(shortlistRun())).toEqual([
      {
        repositoryId: ORDA,
        name: "ORDA",
        uri: "https://doi.org/10.17616/R3D100012124",
        basis: "mandated",
        rationale: "The University asks for its own repository.",
        feeRequired: "unstated",
      },
      // No name in the evidence: the identifier stands in for it.
      {
        repositoryId: ZENODO,
        name: ZENODO,
        uri: null,
        basis: "recommended",
        rationale: "A general repository that mints DataCite DOIs.",
        feeRequired: "yes",
      },
    ]);
  });

  it("finds nothing in a run that is not a shortlist", () => {
    expect(shortlistOf(shortlistRun({ payload: { schema_class: "StandardsAdvice", candidates: [] } }))).toEqual([]);
    expect(shortlistOf(shortlistRun({ payload: null }))).toEqual([]);
  });

  it("reads the repositories named that re3data does not list, with why each was named (#1334)", () => {
    expect(unlistedOf(shortlistRun())).toEqual([{ name: "Netherbrook Local Studies Archive", basis: "in_plan" }]);
    expect(unlistedOf(shortlistRun({ payload: null }))).toEqual([]);
  });
});
