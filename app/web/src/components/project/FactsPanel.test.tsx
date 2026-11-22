import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";

import decidedFixture from "../../../fixtures/project-facts-decided.json";
import forbiddenFixture from "../../../fixtures/project-facts-forbidden.json";
import offeredFixture from "../../../fixtures/project-facts.json";
import { DecisionConflict } from "../../project/api";
import {
  FactForbidden,
  type FactsApi,
  FactsApiContext,
  type ProjectFact,
  type ProjectFacts,
  factKey,
} from "../../project/facts";
import type { Problem } from "../../run/types";
import { factsPath } from "../../route";
import { FactsPanel } from "./FactsPanel";

// What the server says (app/tests/test_project_facts.py): two proposals from the files check, the
// read-back once the duplicate's exclusion is confirmed, and a sensitivity decision refused to a
// member.
const OFFERED = offeredFixture as ProjectFacts;
const DECIDED = decidedFixture as ProjectFacts;
const FORBIDDEN = forbiddenFixture as Problem;
const PROJECT = "01900000-0000-7000-8000-000000000001";

function renderPanel(api: Partial<FactsApi>) {
  const full: FactsApi = {
    facts: () => Promise.resolve(OFFERED),
    decideFact: vi.fn<FactsApi["decideFact"]>(() => Promise.resolve(DECIDED)),
    ...api,
  };
  return render(
    <FactsApiContext.Provider value={full}>
      <FactsPanel projectId={PROJECT} />
    </FactsApiContext.Provider>,
  );
}

async function proposalCard(name: RegExp) {
  return screen.findByRole("article", { name });
}

describe("FactsPanel", () => {
  it("lists each proposal with why it was proposed, and confirms one as it is", async () => {
    const decideFact = vi.fn<FactsApi["decideFact"]>(() => Promise.resolve(DECIDED));
    const { container } = renderPanel({ decideFact });
    const user = userEvent.setup();

    const duplicate = await proposalCard(/Leave data\/old\/readings \(copy\)\.csv out of the deposit/);
    expect(duplicate).toHaveTextContent("byte for byte the same");
    const sites = await proposalCard(/Decide whether calibration\/sites\.csv may be published/);
    expect(sites).toHaveTextContent("Only an owner");
    expect(screen.getByText(/Nobody has decided any facts/)).toBeVisible();
    expect(await axe(container)).toHaveNoViolations();

    await user.click(within(duplicate).getByRole("button", { name: "Confirm" }));

    expect(decideFact).toHaveBeenCalledWith(PROJECT, {
      verdict: "confirmed",
      proposal: OFFERED.proposals[0]?.proposal,
    });
    expect(await screen.findByRole("status")).toHaveTextContent(/Recorded: Leave data\/old/);
    const decided = screen.getByRole("heading", { name: "Decided" }).nextElementSibling as HTMLElement;
    expect(decided).toHaveTextContent(/File to deposit/);
  });

  it("sends a person's own version of a proposal, of the same kind and subject", async () => {
    const decideFact = vi.fn<FactsApi["decideFact"]>(() => Promise.resolve(DECIDED));
    renderPanel({ decideFact });
    const user = userEvent.setup();
    const sites = await proposalCard(/calibration\/sites\.csv/);

    await user.click(within(sites).getByRole("radio", { name: /Change it/ }));
    await user.selectOptions(within(sites).getByLabelText("Whether it may be published"), "generalise");
    await user.selectOptions(within(sites).getByLabelText("At what precision"), "region");
    await user.type(within(sites).getByLabelText(/Reason/), "A curlew nests near one node.");
    await user.click(within(sites).getByRole("button", { name: "Record my version" }));

    expect(decideFact).toHaveBeenCalledWith(PROJECT, {
      verdict: "changed",
      proposal: OFFERED.proposals[1]?.proposal,
      fact: {
        fact_kind: "sensitivity",
        fact_subject: "calibration/sites.csv",
        sensitive_subject: "calibration/sites.csv",
        sensitivity_decision: "generalise",
        location_precision: "region",
      },
      reason: "A curlew nests near one node.",
    });
  });

  it("tells a member that only an owner decides sensitive data, and records nothing", async () => {
    const decideFact = vi.fn<FactsApi["decideFact"]>(() => Promise.reject(new FactForbidden(FORBIDDEN)));
    renderPanel({ decideFact });
    const user = userEvent.setup();
    const sites = await proposalCard(/calibration\/sites\.csv/);

    await user.click(within(sites).getByRole("radio", { name: "Reject it" }));
    await user.click(within(sites).getByRole("button", { name: "Reject" }));

    expect(await within(sites).findByRole("alert")).toHaveTextContent(/Only an owner of this project/);
  });

  it("reads the facts again when a proposal has moved on", async () => {
    const facts = vi
      .fn<FactsApi["facts"]>()
      .mockResolvedValueOnce(OFFERED)
      .mockResolvedValueOnce({ ...OFFERED, proposals: [] });
    const conflict = new DecisionConflict({
      type: "https://w3id.org/data-director/problems/proposal-not-found",
      title: "No such proposal",
      detail: "This project holds no such proposal.",
    });
    renderPanel({ facts, decideFact: () => Promise.reject(conflict) });
    const user = userEvent.setup();
    const duplicate = await proposalCard(/readings \(copy\)/);

    await user.click(within(duplicate).getByRole("button", { name: "Confirm" }));

    expect(await screen.findByRole("status")).toHaveTextContent(/Nothing was recorded/);
    expect(facts).toHaveBeenCalledTimes(2);
    expect(await screen.findByText(/No agent has proposed anything/)).toBeVisible();
  });

  it("records a fact nobody proposed, named by the value that names it", async () => {
    const decideFact = vi.fn<FactsApi["decideFact"]>(() => Promise.resolve(DECIDED));
    renderPanel({ decideFact });
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: /Add a fact/ }));
    const form = screen.getByRole("form", { name: "A fact nobody proposed" });
    await user.selectOptions(within(form).getByLabelText("What the fact is about"), "funder");
    await user.type(within(form).getByLabelText(/The funder's name/), "Natural Environment Research Council");
    await user.click(within(form).getByRole("button", { name: "Record this fact" }));

    expect(decideFact).toHaveBeenCalledWith(PROJECT, {
      verdict: "changed",
      fact: {
        fact_kind: "funder",
        fact_subject: "Natural Environment Research Council",
        fact_funder_name: "Natural Environment Research Council",
      },
    });
  });

  it("removes a fact that stands by rejecting its kind and subject", async () => {
    const decideFact = vi.fn<FactsApi["decideFact"]>(() => Promise.resolve(OFFERED));
    renderPanel({ facts: () => Promise.resolve(DECIDED), decideFact });
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Remove" }));

    const [fact] = DECIDED.decisions;
    expect(decideFact).toHaveBeenCalledWith(PROJECT, {
      verdict: "rejected",
      fact: { fact_kind: fact?.fact_kind, fact_subject: fact?.fact_subject },
    });
    expect(await screen.findByRole("status")).toHaveTextContent(/Removed:/);
  });

  it("confirms a standard the standards advisor proposed, for what it was proposed for", async () => {
    const standard: ProjectFact = {
      fact_kind: "standard",
      fact_subject: "field:species Darwin Core",
      standard_name: "Darwin Core",
      standard_id: "https://doi.org/10.25504/FAIRsharing.xvf5y3",
      standard_kind: "controlled_vocabulary",
      standard_target: "field:species",
      proposed_because: "Recommended by the Standards Librarian; choose it if you will use it.",
    };
    const offered: ProjectFacts = {
      proposals: [
        {
          proposal: "01900000-0000-7000-8000-0000000000d1",
          agent_id: "advisor.standards",
          proposed_at: "2026-11-22T10:00:00Z",
          fact: standard,
        },
      ],
      decisions: [],
    };
    const decideFact = vi.fn<FactsApi["decideFact"]>(() => Promise.resolve(DECIDED));
    const { container } = renderPanel({ facts: () => Promise.resolve(offered), decideFact });
    const user = userEvent.setup();

    const card = await proposalCard(/Use Darwin Core for the field species/);
    expect(await axe(container)).toHaveNoViolations();
    await user.click(within(card).getByRole("button", { name: "Confirm" }));

    expect(decideFact).toHaveBeenCalledWith(PROJECT, {
      verdict: "confirmed",
      proposal: offered.proposals[0]?.proposal,
    });
  });

  it("shows the plan's words for a sharing commitment and keeps them in a correction", async () => {
    const commitment: ProjectFact = {
      fact_kind: "sharing_commitment",
      fact_subject: "Survey responses",
      commitment_repository: "ORDA",
      commitment_quote: "Survey responses will be shared openly in ORDA under CC BY 4.0.",
      commitment_document: "a".repeat(64),
      proposed_because: "Read from dmp.docx; check it against the quoted passage.",
    };
    const offered: ProjectFacts = {
      proposals: [
        {
          proposal: "01900000-0000-7000-8000-0000000000c1",
          agent_id: "advisor.dmp",
          proposed_at: "2026-11-18T10:00:00Z",
          fact: commitment,
        },
      ],
      decisions: [],
    };
    const decideFact = vi.fn<FactsApi["decideFact"]>(() => Promise.resolve(DECIDED));
    const { container } = renderPanel({ facts: () => Promise.resolve(offered), decideFact });
    const user = userEvent.setup();

    const card = await proposalCard(/commits to share Survey responses in ORDA/);
    expect(within(card).getByRole("blockquote")).toHaveTextContent(commitment.commitment_quote ?? "");
    expect(await axe(container)).toHaveNoViolations();

    await user.click(within(card).getByRole("radio", { name: /Change it/ }));
    await user.clear(within(card).getByLabelText(/Where it is shared/));
    await user.type(within(card).getByLabelText(/Where it is shared/), "Zenodo");
    await user.type(within(card).getByLabelText(/Reason/), "We moved to Zenodo.");
    await user.click(within(card).getByRole("button", { name: "Record my version" }));

    const kept: ProjectFact = { ...commitment };
    delete kept.proposed_because;
    expect(decideFact).toHaveBeenCalledWith(PROJECT, {
      verdict: "changed",
      proposal: "01900000-0000-7000-8000-0000000000c1",
      fact: { ...kept, commitment_repository: "Zenodo" },
      reason: "We moved to Zenodo.",
    });
  });

  describe("reached by a link to some of its facts", () => {
    afterEach(() => history.replaceState(null, "", "/"));

    it("marks the facts linked and moves focus to the first", async () => {
      const [, sites] = OFFERED.proposals;
      if (!sites) throw new Error("the fixture has no second proposal");
      history.replaceState(null, "", factsPath(PROJECT, [factKey(sites.fact)]));
      const { container } = renderPanel({});
      const card = await proposalCard(/calibration\/sites\.csv/);
      expect(card).toHaveClass("fact-target");
      expect(card).toHaveFocus();
      const other = screen.getByRole("article", { name: /readings \(copy\)\.csv/ });
      expect(other).not.toHaveClass("fact-target");
      expect(screen.getByRole("link", { name: /without marks/ })).toHaveAttribute("href", factsPath(PROJECT));
      expect(await axe(container)).toHaveNoViolations();
    });

    it("says so when the facts linked are no longer there, and marks nothing", async () => {
      history.replaceState(null, "", factsPath(PROJECT, ["funder:Nobody"]));
      renderPanel({});
      await proposalCard(/calibration\/sites\.csv/);
      expect(screen.getByText(/no longer here/)).toBeVisible();
      expect(document.querySelector(".fact-target")).toBeNull();
    });
  });
});
