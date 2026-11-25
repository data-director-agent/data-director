import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";

import type { ConvertedRecord } from "../../project/conversions";
import type { StandardChoice } from "../../project/standards";
import { ConvertRecord } from "./ConvertRecord";

const PROJECT = "01900000-0000-7000-8000-000000000001";
const DATACITE = {
  conforms_to: "http://datacite.org/schema/kernel-4",
  title: "DataCite Metadata Schema 4",
};
const DUBLIN_CORE = {
  conforms_to: "http://www.openarchives.org/OAI/2.0/oai_dc/",
  title: "Dublin Core (OAI-DC)",
};
const CHOICE: StandardChoice = {
  standard: { title: DATACITE.title, reason: "declared", chosen_by: null },
  standards: [DATACITE, DUBLIN_CORE],
  may_choose: true,
};
const MADE: ConvertedRecord = {
  digest: "a".repeat(64),
  conforms_to: DUBLIN_CORE.conforms_to,
  media_type: "application/xml",
  title: "Dublin Core",
  derived_from: "b".repeat(64),
  unplaced: ["fundingReferences"],
  reduced: [
    { path: "creators", reason: "its affiliation has no place in Dublin Core" },
  ],
  made_at: "2026-11-25T10:00:00Z",
};

/** A fetch that answers each request by its method and path, in the server's shapes. */
function serving(convert: [number, unknown], earlier: ConvertedRecord[] = []) {
  const fetched = vi.fn((url: string, init?: RequestInit) => {
    const reply = (status: number, body: unknown) =>
      Promise.resolve(new Response(JSON.stringify(body), { status }));
    if (url.endsWith("/repository/standard")) return reply(200, CHOICE);
    if (init?.method === "POST") return reply(...convert);
    return reply(200, { conversions: earlier });
  });
  vi.stubGlobal("fetch", fetched);
  return fetched;
}

async function convertTo(standard: string) {
  await userEvent.selectOptions(await screen.findByRole("combobox"), standard);
  await userEvent.click(
    screen.getByRole("button", { name: "Convert the approved record" }),
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("ConvertRecord", () => {
  it("offers only the standards the record is not already in", async () => {
    serving([201, MADE]);
    const { container } = render(
      <ConvertRecord projectId={PROJECT} revision={0} />,
    );
    const select = await screen.findByRole("combobox");
    const offered = within(select)
      .getAllByRole("option")
      .map((o) => (o as HTMLOptionElement).value);
    expect(offered).toContain(DUBLIN_CORE.conforms_to);
    expect(offered).not.toContain(DATACITE.conforms_to);
    expect(await axe(container)).toHaveNoViolations();
  });

  it("converts the record and lists what was lost, with a link to download it", async () => {
    const fetched = serving([201, MADE]);
    render(<ConvertRecord projectId={PROJECT} revision={0} />);
    await convertTo(DUBLIN_CORE.conforms_to);
    const kept = await screen.findByRole("list", { name: "Converted records" });
    const link = within(kept).getByRole("link");
    expect(link).toHaveAttribute(
      "href",
      `/api/projects/${PROJECT}/conversions/${MADE.digest}`,
    );
    expect(within(kept).getByText("fundingReferences")).toBeVisible();
    expect(within(kept).getByText("creators")).toBeVisible();
    const post = fetched.mock.calls.find(([, init]) => init?.method === "POST");
    expect(JSON.parse(post?.[1]?.body as string)).toEqual({
      conforms_to: DUBLIN_CORE.conforms_to,
    });
  });

  it("shows what to add to the record when the target requires what it lacks", async () => {
    serving([
      409,
      {
        type: "https://w3id.org/data-director/problems/conversion-refused",
        title: "Conversion refused",
        status: 409,
        detail:
          "Dublin Core requires what the approved record does not give: Title.",
        missing: [
          { property: "title", label: "Title", question: "Add a title" },
        ],
      },
    ]);
    render(<ConvertRecord projectId={PROJECT} revision={0} />);
    await convertTo(DUBLIN_CORE.conforms_to);
    const alert = await screen.findByRole("alert");
    expect(within(alert).getAllByRole("listitem")).toHaveLength(1);
    expect(
      screen.queryByRole("list", { name: "Converted records" }),
    ).not.toBeInTheDocument();
  });

  it("lists the conversions kept before", async () => {
    serving([201, MADE], [MADE]);
    render(<ConvertRecord projectId={PROJECT} revision={0} />);
    const kept = await screen.findByRole("list", { name: "Converted records" });
    expect(within(kept).getAllByRole("link")).toHaveLength(1);
  });
});
