import { render, screen } from "@testing-library/react";
import { axe } from "jest-axe";

import type { SourceCredit } from "../../sources/credits";
import { SourcesPage } from "./SourcesPage";

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
  terms_url: "https://fairsharing.org/licence",
  citation: "Sansone et al. 2019",
  badge_url: "https://api.fairsharing.org/img/fairsharing-attribution.svg",
  match: { source_id_prefixes: ["FAIRsharing."], snapshot_ref_prefixes: [] },
};
const ORCID: SourceCredit = {
  ...FAIRSHARING,
  id: "orcid",
  name: "ORCID",
  kind: "service",
  licence: "LicenseRef-ORCID-public-API-terms",
  attribution: "Public data from ORCID",
  non_commercial: true,
  use: "live",
  terms_url: null,
  citation: null,
  badge_url: null,
};

describe("SourcesPage", () => {
  it("shows each source's credit as written, its licence and its badge", async () => {
    render(<SourcesPage load={() => Promise.resolve([FAIRSHARING, ORCID])} />);
    expect(screen.getByRole("heading", { level: 1, name: "Sources and licences" })).toBeVisible();
    expect(await screen.findByText(FAIRSHARING.attribution)).toBeVisible();
    expect(screen.getByRole("link", { name: /CC-BY-SA-4\.0/ })).toHaveAttribute(
      "href",
      FAIRSHARING.licence_url,
    );
    expect(screen.getByRole("img", { name: /FAIRsharing attribution badge/ })).toBeVisible();
  });

  it("flags a source whose own terms are non-commercial", async () => {
    render(<SourcesPage load={() => Promise.resolve([FAIRSHARING, ORCID])} />);
    expect(await screen.findByText("Non-commercial terms")).toBeVisible();
    expect(screen.getAllByText("Non-commercial terms")).toHaveLength(1);
  });

  it("says so when the list cannot be read", async () => {
    render(<SourcesPage load={() => Promise.reject(new Error("no answer"))} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("no answer");
  });

  it("has no accessibility violations", async () => {
    const { container } = render(<SourcesPage load={() => Promise.resolve([FAIRSHARING, ORCID])} />);
    await screen.findByText(FAIRSHARING.attribution);
    expect(await axe(container)).toHaveNoViolations();
  });
});
