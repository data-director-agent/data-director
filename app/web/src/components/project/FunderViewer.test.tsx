import { render, screen } from "@testing-library/react";
import { axe } from "jest-axe";

import organisationFixture from "../../../fixtures/funder-ror-organisation.json";
import type { ProjectFact, ProjectFacts } from "../../project/facts";
import {
  type FundersApi,
  FundersApiContext,
  OrganisationNotFound,
  type RorOrganisation,
} from "../../project/funders";
import { factsPath } from "../../route";
import { FunderViewer } from "./FunderViewer";

// What the server says (app/tests/test_funders.py): UKRI as the pinned ROR dump records it.
const UKRI = organisationFixture as RorOrganisation;
const PROJECT = "01900000-0000-7000-8000-000000000001";
const SUBJECT = "UKRI";

function funder(extra: Record<string, string> = {}): ProjectFact {
  return {
    fact_kind: "funder",
    fact_subject: SUBJECT,
    fact_funder_name: "UK Research and Innovation",
    fact_funder_ror: "001aqnf71",
    ...extra,
  } as ProjectFact;
}

function facts(decided: ProjectFact[], proposed: ProjectFact[] = []): ProjectFacts {
  return {
    decisions: decided,
    proposals: proposed.map((fact, i) => ({
      proposal: `proposal-${i}`,
      agent_id: "advisor.policy",
      proposed_at: "2026-11-20T10:00:00Z",
      fact,
    })),
  } as ProjectFacts;
}

function renderViewer(held: ProjectFacts, api: Partial<FundersApi> = {}) {
  const full: FundersApi = { organisation: () => Promise.resolve(UKRI), ...api };
  return render(
    <FundersApiContext.Provider value={full}>
      <FunderViewer projectId={PROJECT} subject={SUBJECT} facts={held} />
    </FundersApiContext.Provider>,
  );
}

describe("FunderViewer", () => {
  it("shows the decided fact with the organisation behind its ROR identifier", async () => {
    const organisation = vi.fn<FundersApi["organisation"]>(() => Promise.resolve(UKRI));
    const { container } = renderViewer(facts([funder()]), { organisation });

    expect(await screen.findByRole("heading", { name: "UK Research and Innovation" })).toBeVisible();
    expect(organisation).toHaveBeenCalledWith("001aqnf71", expect.any(AbortSignal));
    expect(screen.getByRole("link", { name: UKRI.ror_id })).toHaveAttribute("href", UKRI.links.ror);
    expect(screen.getByRole("link", { name: "100014013" })).toHaveAttribute(
      "href",
      UKRI.links.crossref_funders[0],
    );
    expect(screen.getByRole("link", { name: /Back to the project's facts/ })).toHaveAttribute(
      "href",
      factsPath(PROJECT),
    );
    expect(await axe(container)).toHaveNoViolations();
  });

  it("shows a proposal that waits for a decision", async () => {
    renderViewer(facts([], [funder()]));
    expect(await screen.findByText(/Proposed by advisor\.policy/)).toBeVisible();
  });

  it("says when no ROR identifier is recorded, without asking the server", () => {
    const organisation = vi.fn<FundersApi["organisation"]>();
    renderViewer(facts([funder({ fact_funder_ror: "" })]), { organisation });
    expect(screen.getByText(/No ROR identifier is recorded/)).toBeVisible();
    expect(organisation).not.toHaveBeenCalled();
  });

  it("says when the dump holds no such organisation", async () => {
    renderViewer(facts([funder()]), {
      organisation: () => Promise.reject(new OrganisationNotFound("none")),
    });
    expect(await screen.findByRole("alert")).toHaveTextContent("holds no organisation");
  });

  it("says when the record could not be read", async () => {
    renderViewer(facts([funder()]), {
      organisation: () => Promise.reject(new Error("The dump is not built.")),
    });
    expect(await screen.findByRole("alert")).toHaveTextContent("The dump is not built.");
  });

  it("warns when the recorded Crossref Funder ID is not one ROR holds", async () => {
    renderViewer(facts([funder({ fact_crossref_funder_id: "999" })]));
    expect(await screen.findByRole("note")).toHaveTextContent("999");
  });

  it("accepts a Crossref Funder ID with its DOI prefix", async () => {
    renderViewer(facts([funder({ fact_crossref_funder_id: "10.13039/100014013" })]));
    await screen.findByRole("heading", { name: "UK Research and Innovation" });
    expect(screen.queryByRole("note")).not.toBeInTheDocument();
  });

  it("says when the project holds no such funder", () => {
    renderViewer(facts([]));
    expect(screen.getByText(/holds no funder fact/)).toBeVisible();
  });
});
