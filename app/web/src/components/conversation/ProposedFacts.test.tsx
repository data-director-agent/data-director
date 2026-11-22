import { render, screen } from "@testing-library/react";
import { axe } from "jest-axe";

import offeredFixture from "../../../fixtures/project-facts.json";
import { type ProjectFact, type ProjectFacts, factKey } from "../../project/facts";
import { ProposedFacts } from "./ProposedFacts";

const FACTS: ProjectFact[] = (offeredFixture as ProjectFacts).proposals.map((p) => p.fact as ProjectFact);
const PROJECT = "01900000-0000-7000-8000-000000000001";

describe("ProposedFacts", () => {
  it("lists what a run proposed and links to those facts on the project's facts page", async () => {
    const { container } = render(<ProposedFacts facts={FACTS} projectId={PROJECT} />);
    expect(screen.getAllByRole("listitem")).toHaveLength(FACTS.length);
    const href = new URL(screen.getByRole("link").getAttribute("href") ?? "", location.origin);
    expect(href.pathname).toBe(`/projects/${PROJECT}/facts`);
    expect(href.searchParams.getAll("fact")).toEqual(FACTS.map(factKey));
    expect(await axe(container)).toHaveNoViolations();
  });

  it("lists a few and counts the rest, so the card stays short", () => {
    const many = Array.from({ length: 6 }, (_, i): ProjectFact => ({ fact_kind: "funder", fact_subject: `F${i}` }));
    render(<ProposedFacts facts={many} projectId={PROJECT} />);
    expect(screen.getAllByRole("listitem").length).toBeLessThan(many.length);
    expect(new URL(screen.getByRole("link").getAttribute("href") ?? "", location.origin).searchParams.getAll("fact")).toEqual(
      many.map(factKey),
    );
  });

  it("draws no link in a conversation with no project, and nothing when none was proposed", () => {
    const { rerender, container } = render(<ProposedFacts facts={FACTS} projectId={null} />);
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
    rerender(<ProposedFacts facts={[]} projectId={PROJECT} />);
    expect(container).toBeEmptyDOMElement();
  });
});
