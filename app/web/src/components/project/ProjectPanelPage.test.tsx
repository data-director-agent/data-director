import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";

import { type ProjectApi, ProjectApiContext } from "../../project/api";
import {
  PROJECT,
  REPOSITORY,
  SUGGESTED,
  at,
  fakeProjectApi as fakeApi,
} from "../../test/projectApi";
import { type PanelTab, ProjectPanelPage } from "./ProjectPanelPage";

function renderPage(api: ProjectApi, tab: PanelTab) {
  return render(
    <ProjectApiContext.Provider value={api}>
      <ProjectPanelPage projectId={PROJECT.project_id} tab={tab} />
    </ProjectApiContext.Provider>,
  );
}

function tab(name: string) {
  return within(screen.getByRole("navigation", { name: "Project" })).getByRole(
    "link",
    { name },
  );
}

describe("ProjectPanelPage", () => {
  it("shows how generative AI was used, on its own tab", async () => {
    const { container } = renderPage(fakeApi(), "ai-use");
    expect(
      await screen.findByRole("heading", { name: "Use of generative AI" }),
    ).toBeVisible();
    expect(tab("Use of generative AI")).toHaveAttribute("aria-current", "page");
    expect(screen.queryByRole("article")).not.toBeInTheDocument();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("opens the project's facts, for a person to decide what agents proposed", async () => {
    const offered = { proposals: [], decisions: [] };
    vi.stubGlobal(
      "fetch",
      // Only the facts are answered; the page's other reads, as of its data stewards, are not.
      vi.fn((url: string) =>
        Promise.resolve(
          url.endsWith("/facts") ? new Response(JSON.stringify(offered)) : new Response(null, { status: 404 }),
        ),
      ),
    );
    try {
      renderPage(fakeApi(), "facts");
      const panel = await screen.findByRole("region", {
        name: "Project facts",
      });
      expect(
        await within(panel).findByText(/No agent has proposed anything/),
      ).toBeVisible();
      expect(tab("Project facts")).toHaveAttribute("aria-current", "page");
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it("shows the repository chosen, what it asks for and what Data Director assumes", async () => {
    const { container } = renderPage(fakeApi(), "repository");
    const panel = await screen.findByRole("region", { name: "Repository" });
    expect(
      await within(panel).findByRole("link", { name: /^ORDA/ }),
    ).toHaveAttribute(
      "href",
      "https://www.re3data.org/repository/r3d100012124",
    );
    const site = REPOSITORY.repository_url ?? "";
    expect(within(panel).getByRole("link", { name: site })).toHaveAttribute(
      "href",
      site,
    );
    expect(within(panel).getByText("orda@v3")).toBeVisible();
    expect(
      within(panel).getByRole("heading", { name: "What it accepts" }),
    ).toBeVisible();
    expect(
      within(panel).getByRole("heading", {
        name: "What Data Director assumes",
      }),
    ).toBeVisible();
    for (const item of REPOSITORY.unconfirmed ?? []) {
      expect(within(panel).getByText(item)).toBeVisible();
    }
    expect(
      within(panel).getByRole("heading", {
        name: "Metadata the record must have",
      }),
    ).toBeVisible();
    expect(within(panel).getByText("Title")).toBeVisible();
    const sources = within(panel).getByRole("heading", {
      name: "Where this comes from",
    });
    const list = sources.nextElementSibling as HTMLElement;
    expect(
      within(list)
        .getAllByRole("link")
        .map((a) => a.getAttribute("href")),
    ).toEqual(REPOSITORY.guidance);
    expect(tab("Repository")).toHaveAttribute("aria-current", "page");
    expect(await axe(container)).toHaveNoViolations();
  });

  it("leaves out what the repository's sets do not state", async () => {
    const bare = {
      ...REPOSITORY,
      media_types: [],
      licences: [],
      unconfirmed: [],
      guidance: [],
      warnings: ["Checked against the standard alone."],
    };
    delete (bare as Partial<typeof bare>).repository_url;
    renderPage(
      fakeApi({ repository: () => Promise.resolve(bare) }),
      "repository",
    );
    const panel = await screen.findByRole("region", { name: "Repository" });
    expect(
      await within(panel).findByText("Checked against the standard alone."),
    ).toBeVisible();
    expect(
      within(panel).queryByRole("heading", { name: "What it accepts" }),
    ).toBeNull();
    expect(
      within(panel).queryByRole("heading", { name: "Where this comes from" }),
    ).toBeNull();
    expect(within(panel).queryByText("Where to deposit")).toBeNull();
  });

  it("says how to choose a repository when none has been", async () => {
    renderPage(
      fakeApi({ repository: () => Promise.resolve(null) }),
      "repository",
    );
    expect(
      await screen.findByText(/No repository has been chosen yet/),
    ).toBeVisible();
  });

  it("chooses a suggested repository on the tab and shows what it asks for", async () => {
    const user = userEvent.setup();
    const choose = vi
      .fn<ProjectApi["chooseRepository"]>()
      .mockResolvedValue(REPOSITORY);
    const { container } = renderPage(
      fakeApi({
        repository: () => Promise.resolve(null),
        chooseRepository: choose,
      }),
      "repository",
    );
    const box = await screen.findByRole("combobox", {
      name: "Find a repository",
    });
    expect(
      screen.getByRole("button", { name: "Choose repository" }),
    ).toBeDisabled();
    await user.click(box);
    const options = await screen.findAllByRole("option");
    expect(options.map((o) => o.textContent)).toEqual(
      SUGGESTED.repositories.map(
        (r) => expect.stringContaining(r.name) as unknown,
      ),
    );
    expect(await axe(container)).toHaveNoViolations();
    await user.click(at(options, 0));
    await user.click(screen.getByRole("button", { name: "Choose repository" }));
    expect(choose).toHaveBeenCalledWith(
      PROJECT.project_id,
      at(SUGGESTED.repositories, 0).repository_id,
    );
    const panel = screen.getByRole("region", { name: "Repository" });
    expect(await within(panel).findByText("orda@v3")).toBeVisible();
    expect(
      within(panel).getByRole("button", { name: "Change repository" }),
    ).toBeVisible();
  });

  it("searches re3data with what is typed", async () => {
    const user = userEvent.setup();
    const search = vi.fn<ProjectApi["searchRepositories"]>((query) =>
      Promise.resolve({
        ...SUGGESTED,
        query,
        suggested: !query,
        repositories: query
          ? SUGGESTED.repositories.slice(1)
          : SUGGESTED.repositories,
      }),
    );
    renderPage(fakeApi({ searchRepositories: search }), "repository");
    await user.click(
      await screen.findByRole("button", { name: "Change repository" }),
    );
    await user.type(
      screen.getByRole("combobox", { name: "Find a repository" }),
      "zen",
    );
    await vi.waitFor(() =>
      expect(search).toHaveBeenLastCalledWith("zen", expect.anything()),
    );
    const options = await screen.findAllByRole("option");
    expect(options).toHaveLength(1);
    expect(at(options, 0)).toHaveTextContent(
      at(SUGGESTED.repositories, 1).name,
    );
  });

  it("offers the deposit package on its own tab", async () => {
    const { container } = renderPage(fakeApi(), "deposit");
    expect(
      await screen.findByRole("heading", { name: "Deposit package" }),
    ).toBeVisible();
    expect(tab("Deposit package")).toHaveAttribute("aria-current", "page");
    expect(
      screen.getByRole("button", { name: "Check the project" }),
    ).toBeVisible();
    expect(await axe(container)).toHaveNoViolations();
  });
});
