import { render, screen } from "@testing-library/react";

import { type SourceCredit, SourceCreditsContext } from "../../sources/credits";
import type { Checks, EvidenceItem } from "../../run/types";
import { EvidencePanel } from "./EvidencePanel";

const CHECKS = { grounding: null, sources: null } as unknown as Checks;
const FAIRSHARING: SourceCredit = {
  id: "fairsharing",
  name: "FAIRsharing",
  url: "https://fairsharing.org",
  kind: "data",
  licence: "CC-BY-SA-4.0",
  licence_url: "https://creativecommons.org/licenses/by-sa/4.0/",
  attribution: "FAIRsharing content is licensed under CC BY-SA 4.0.",
  credit_required: true,
  non_commercial: false,
  use: "both",
  terms_url: null,
  citation: null,
  badge_url: null,
  match: { source_id_prefixes: ["FAIRsharing."], snapshot_ref_prefixes: [] },
};

function item(source_id: string): EvidenceItem {
  return {
    source_id,
    source_uri: null,
    snapshot_ref: null,
    retrieved_at: null,
    content: { name: "A record" },
  } as unknown as EvidenceItem;
}

describe("EvidencePanel", () => {
  it("names the source of an item and its licence, linking to the sources page", () => {
    render(
      <SourceCreditsContext.Provider value={[FAIRSHARING]}>
        <EvidencePanel evidence={[item("FAIRsharing.abc123")]} checks={CHECKS} idPrefix="r" />
      </SourceCreditsContext.Provider>,
    );
    expect(screen.getByRole("link", { name: "FAIRsharing" })).toHaveAttribute(
      "href",
      "/sources#source-fairsharing",
    );
    expect(screen.getByRole("link", { name: "CC-BY-SA-4.0" })).toHaveAttribute(
      "href",
      FAIRSHARING.licence_url,
    );
  });

  it("shows no credit line for an item no source claims", () => {
    render(
      <SourceCreditsContext.Provider value={[FAIRSHARING]}>
        <EvidencePanel evidence={[item("input:1")]} checks={CHECKS} idPrefix="r" />
      </SourceCreditsContext.Provider>,
    );
    expect(screen.queryByText(/Source:/)).toBeNull();
  });
});
