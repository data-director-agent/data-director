import { creditFor, type SourceCredit } from "./credits";

function source(id: string, source_id_prefixes: string[], snapshot_ref_prefixes: string[]): SourceCredit {
  return {
    id,
    name: id,
    url: "https://example.org",
    kind: "data",
    licence: "CC0-1.0",
    licence_url: "https://example.org/licence",
    attribution: id,
    credit_required: false,
    non_commercial: false,
    use: "pinned",
    terms_url: null,
    citation: null,
    badge_url: null,
    match: { source_id_prefixes, snapshot_ref_prefixes },
  };
}

const SOURCES = [
  source("fairsharing", ["FAIRsharing."], ["snapshot:"]),
  source("ror", ["tool:ror/"], ["ror:"]),
];

describe("creditFor", () => {
  it("names a source by the start of an item's source_id", () => {
    expect(creditFor({ source_id: "FAIRsharing.abc123" }, SOURCES)?.id).toBe("fairsharing");
    expect(creditFor({ source_id: "tool:ror/05x" }, SOURCES)?.id).toBe("ror");
  });

  it("names a source by the start of its snapshot_ref when the id does not say", () => {
    expect(creditFor({ source_id: "05x2", snapshot_ref: "ror:dump:v2.15" }, SOURCES)?.id).toBe("ror");
  });

  it("names none where the list does not say", () => {
    expect(creditFor({ source_id: "input:1", snapshot_ref: null }, SOURCES)).toBeNull();
    expect(creditFor({ source_id: "x" }, [])).toBeNull();
  });
});
