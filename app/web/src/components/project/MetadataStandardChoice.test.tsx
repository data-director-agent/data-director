import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";

import type { ChosenStandard, StandardChoice } from "../../project/standards";
import { MetadataStandardChoice } from "./MetadataStandardChoice";

const PROJECT = "01900000-0000-7000-8000-000000000001";
const DATACITE = {
  conforms_to: "http://datacite.org/schema/kernel-4",
  title: "DataCite Metadata Schema 4",
};
const DUBLIN_CORE = {
  conforms_to: "http://www.openarchives.org/OAI/2.0/oai_dc/",
  title: "Dublin Core (OAI-DC)",
};

function choice(standard: ChosenStandard, mayChoose = true): StandardChoice {
  return {
    standard,
    standards: [DATACITE, DUBLIN_CORE],
    may_choose: mayChoose,
  };
}

function answering(...bodies: [number, unknown][]) {
  const fetched = vi.fn();
  for (const [status, body] of bodies) {
    fetched.mockResolvedValueOnce(
      new Response(JSON.stringify(body), { status }),
    );
  }
  vi.stubGlobal("fetch", fetched);
  return fetched;
}

afterEach(() => vi.unstubAllGlobals());

describe("MetadataStandardChoice", () => {
  it("says the standard was assumed when re3data lists none the deployment has a set for", async () => {
    answering([
      200,
      choice({ title: DATACITE.title, reason: "fallback", chosen_by: null }),
    ]);
    const { container } = render(
      <MetadataStandardChoice
        projectId={PROJECT}
        revision={0}
        onChosen={vi.fn()}
      />,
    );
    const said = await screen.findByText(/assumed/);
    expect(said.closest("p")).toHaveClass("status-warn");
    expect(await axe(container)).toHaveNoViolations();
  });

  it("names who chose a standard", async () => {
    answering([
      200,
      choice({
        title: DUBLIN_CORE.title,
        reason: "chosen",
        chosen_by: "Josiah Carberry",
      }),
    ]);
    render(
      <MetadataStandardChoice
        projectId={PROJECT}
        revision={0}
        onChosen={vi.fn()}
      />,
    );
    expect(await screen.findByText(/Josiah Carberry chose it/)).toBeVisible();
  });

  it("offers no choice when the repository's settings name the standard", async () => {
    answering([
      200,
      choice(
        { title: DATACITE.title, reason: "override", chosen_by: null },
        false,
      ),
    ]);
    render(
      <MetadataStandardChoice
        projectId={PROJECT}
        revision={0}
        onChosen={vi.fn()}
      />,
    );
    expect(
      await screen.findByText(/settings for the repository name it/),
    ).toBeVisible();
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
  });

  it("chooses another standard and says the panel should read the requirements again", async () => {
    const fetched = answering(
      [
        200,
        choice({ title: DATACITE.title, reason: "declared", chosen_by: null }),
      ],
      [
        201,
        choice({
          title: DUBLIN_CORE.title,
          reason: "chosen",
          chosen_by: "Josiah Carberry",
        }),
      ],
    );
    const onChosen = vi.fn();
    render(
      <MetadataStandardChoice
        projectId={PROJECT}
        revision={0}
        onChosen={onChosen}
      />,
    );
    await userEvent.selectOptions(
      await screen.findByRole("combobox"),
      DUBLIN_CORE.conforms_to,
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Use this standard" }),
    );
    expect(await screen.findByText(/Josiah Carberry chose it/)).toBeVisible();
    const [url, init] = fetched.mock.calls[1] as unknown as [
      string,
      RequestInit,
    ];
    expect(url).toBe(`/api/projects/${PROJECT}/repository/standard`);
    expect(init.method).toBe("PUT");
    expect(JSON.parse(init.body as string)).toEqual({
      conforms_to: DUBLIN_CORE.conforms_to,
    });
    expect(onChosen).toHaveBeenCalled();
  });

  it("shows a refused choice in the server's words", async () => {
    answering(
      [
        200,
        choice({ title: DATACITE.title, reason: "declared", chosen_by: null }),
      ],
      [
        400,
        {
          type: "https://w3id.org/data-director/problems/request-refused",
          title: "Refused",
          status: 400,
          detail: "no set for it",
        },
      ],
    );
    render(
      <MetadataStandardChoice
        projectId={PROJECT}
        revision={0}
        onChosen={vi.fn()}
      />,
    );
    await userEvent.selectOptions(
      await screen.findByRole("combobox"),
      DUBLIN_CORE.conforms_to,
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Use this standard" }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent("no set for it");
  });

  it("shows nothing while no repository is chosen", async () => {
    const fetched = answering([
      404,
      {
        type: "https://w3id.org/data-director/problems/repository-not-chosen",
        title: "No repository chosen",
        status: 404,
      },
    ]);
    const { container } = render(
      <MetadataStandardChoice
        projectId={PROJECT}
        revision={0}
        onChosen={vi.fn()}
      />,
    );
    await vi.waitFor(() => expect(fetched).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });
});
