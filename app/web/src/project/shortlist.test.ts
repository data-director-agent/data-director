import { shortlistOf } from "./shortlist";
import { ORDA, ZENODO, shortlistRun } from "../test/shortlist";

describe("shortlistOf", () => {
  it("names each candidate by the re3data record it rests on, in the advisor's order", () => {
    expect(shortlistOf(shortlistRun())).toEqual([
      {
        re3dataId: ORDA,
        name: "ORDA",
        uri: "https://doi.org/10.17616/R3D100012124",
        basis: "mandated",
        rationale: "The University asks for its own repository.",
      },
      // No name in the evidence: the identifier stands in for it.
      {
        re3dataId: ZENODO,
        name: ZENODO,
        uri: null,
        basis: "recommended",
        rationale: "A general repository that mints DataCite DOIs.",
      },
    ]);
  });

  it("finds nothing in a run that is not a shortlist", () => {
    expect(shortlistOf(shortlistRun({ payload: { schema_class: "StandardsAdvice", candidates: [] } }))).toEqual([]);
    expect(shortlistOf(shortlistRun({ payload: null }))).toEqual([]);
  });
});
