import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";

import offeredFixture from "../../../fixtures/orcid-record.json";
import lastOwnerFixture from "../../../fixtures/project-members-last-owner.json";
import membersFixture from "../../../fixtures/project-members.json";
import keptFixture from "../../../fixtures/project-researchers.json";
import { ActiveProjectTestContext } from "../../project/active";
import { type ProjectApi, ProjectApiContext } from "../../project/api";
import { type MembersApi, MembersApiContext, MembersRefused, type ProjectMembers } from "../../project/members";
import type { ResearcherRecord } from "../../project/researcher";
import type { Problem } from "../../run/types";
import { PeoplePanel } from "./PeoplePanel";

// What the server says (app/tests/test_project_members.py): an owner, and the colleague they added.
// (app/tests/test_researcher_facts.py): the sample public record, and what the person kept of it.
const OWNED = membersFixture as ProjectMembers;
const OFFERED = offeredFixture as ResearcherRecord;
const KEPT = keptFixture as ResearcherRecord[];
const LAST_OWNER = lastOwnerFixture as Problem;
const PROJECT = "01900000-0000-7000-8000-000000000001";
const COLLEAGUE = "https://orcid.org/0000-0002-1694-233X";
const ME = "https://orcid.org/0000-0002-1825-0097";

/** The same project as its plain member sees it: no managing, and leaving allowed. */
const JOINED: ProjectMembers = {
  former_researchers: [],
  your_role: "member",
  may_manage: false,
  may_leave: true,
  members: OWNED.members.map((m) => ({
    ...m,
    is_you: m.member_id === COLLEAGUE,
    removable: m.member_id === COLLEAGUE,
    role_changeable: false,
  })),
};

/** The owner's view once they have kept facts from their ORCID record. */
const KEPT_BY_ME: ProjectMembers = {
  ...OWNED,
  members: OWNED.members.map((m) => (m.is_you ? { ...m, record: KEPT[0] as ResearcherRecord } : m)),
};

function renderPanel(api: Partial<MembersApi>, reloadProjects = vi.fn(), project: Partial<ProjectApi> = {}) {
  const projectApi = {
    orcidRecord: () => Promise.resolve(OFFERED),
    ...project,
  } as unknown as ProjectApi;
  const full: MembersApi = {
    members: () => Promise.resolve(OWNED),
    addMember: () => Promise.resolve(OWNED),
    changeRole: () => Promise.resolve(OWNED),
    removeMember: () => Promise.resolve(OWNED),
    ...api,
  };
  return render(
    <ActiveProjectTestContext.Provider
      value={{
        projectId: PROJECT,
        projects: [],
        setProjectId: vi.fn(),
        reloadProjects,
      }}
    >
      <ProjectApiContext.Provider value={projectApi}>
        <MembersApiContext.Provider value={full}>
          <PeoplePanel projectId={PROJECT} />
        </MembersApiContext.Provider>
      </ProjectApiContext.Provider>
    </ActiveProjectTestContext.Provider>,
  );
}

/** The members' entries: the first list's own items, not those of the facts within them. */
function entries(): HTMLElement[] {
  const list = screen.getAllByRole("list")[0] as HTMLElement;
  return within(list)
    .getAllByRole("listitem")
    .filter((item) => item.parentElement === list);
}

describe("PeoplePanel", () => {
  it("shows an owner each member by name or ORCID iD, and the controls the server offers", async () => {
    const { container } = renderPanel({});
    await screen.findAllByRole("list");
    const [me, colleague] = entries() as [HTMLElement, HTMLElement];
    expect(entries()).toHaveLength(2);
    expect(me).toHaveTextContent("(you)");
    // The owner is named from their public ORCID record; the colleague, who has none, by iD.
    expect(within(me).getByRole("heading", { level: 3 })).toHaveTextContent(OWNED.members[0]?.public_name ?? "");
    expect(within(me).getByRole("link")).toHaveAttribute("href", ME);
    expect(within(colleague).getByRole("heading", { level: 3 })).toHaveTextContent("0000-0002-1694-233X");
    // The last owner is neither demoted nor removed, and only their own facts are theirs to change;
    // the colleague may be both demoted and removed.
    expect(within(me).queryByRole("button", { name: /Make|Remove/ })).toBeNull();
    expect(
      within(me).getByRole("button", {
        name: /Bring in facts from your ORCID record/,
      }),
    ).toBeVisible();
    expect(within(colleague).queryByRole("button", { name: /ORCID/ })).toBeNull();
    expect(within(colleague).getByRole("button", { name: /Make owner/ })).toBeVisible();
    expect(within(colleague).getByRole("button", { name: /Remove/ })).toBeVisible();
    expect(screen.getByRole("form", { name: "Add a member" })).toBeVisible();
    expect(screen.queryByRole("button", { name: "Leave this project" })).toBeNull();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("offers a plain member only leaving", async () => {
    renderPanel({ members: () => Promise.resolve(JOINED) });
    expect(await screen.findByRole("button", { name: "Leave this project" })).toBeVisible();
    expect(screen.queryByRole("form", { name: "Add a member" })).toBeNull();
    expect(screen.queryByRole("button", { name: /Make owner|Make member|Remove/ })).toBeNull();
  });

  it("adds a person by ORCID iD and says so", async () => {
    const addMember = vi.fn(() => Promise.resolve(OWNED));
    renderPanel({ addMember });
    const user = userEvent.setup();
    const field = await screen.findByRole("textbox", {
      name: "Their ORCID iD",
    });
    await user.type(field, "0000-0002-1694-233X");
    await user.click(screen.getByRole("radio", { name: /^Owner/ }));
    await user.click(screen.getByRole("button", { name: "Add to the project" }));
    expect(addMember).toHaveBeenCalledWith(PROJECT, "0000-0002-1694-233X", "owner");
    expect(await screen.findByRole("status")).toHaveTextContent(/Added 0000-0002-1694-233X/);
    expect(field).toHaveValue("");
  });

  it("keeps what was typed when the server refuses it", async () => {
    const addMember = vi.fn(() =>
      Promise.reject(
        new MembersRefused({
          ...LAST_OWNER,
          type: "already-member",
          detail: "already a member",
        }),
      ),
    );
    renderPanel({ addMember });
    const user = userEvent.setup();
    const field = await screen.findByRole("textbox", {
      name: "Their ORCID iD",
    });
    await user.type(field, ME);
    await user.click(screen.getByRole("button", { name: "Add to the project" }));
    expect(await screen.findByRole("status")).toHaveTextContent(/already a member/);
    expect(field).toHaveValue(ME);
  });

  it("asks before removing a member", async () => {
    const removeMember = vi.fn(() => Promise.resolve({ ...OWNED, members: OWNED.members.slice(0, 1) }));
    renderPanel({ removeMember });
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: /Remove/ }));
    const dialog = await screen.findByRole("dialog", {
      name: "Remove a member",
    });
    expect(removeMember).not.toHaveBeenCalled();
    await user.click(within(dialog).getByRole("button", { name: "Remove" }));
    expect(removeMember).toHaveBeenCalledWith(PROJECT, COLLEAGUE);
    expect(await screen.findByRole("status")).toHaveTextContent(/no longer a member/);
    expect(entries()).toHaveLength(1);
  });

  it("leaves after asking, and goes back to the projects", async () => {
    const removeMember = vi.fn(() => Promise.resolve(null));
    const reloadProjects = vi.fn();
    renderPanel({ members: () => Promise.resolve(JOINED), removeMember }, reloadProjects);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Leave this project" }));
    const dialog = await screen.findByRole("dialog", {
      name: "Leave this project",
    });
    await user.click(within(dialog).getByRole("button", { name: "Leave" }));
    expect(removeMember).toHaveBeenCalledWith(PROJECT, COLLEAGUE);
    await vi.waitFor(() => expect(reloadProjects).toHaveBeenCalled());
    expect(window.location.pathname).toBe("/projects");
  });

  it("says when the members cannot be read", async () => {
    renderPanel({ members: () => Promise.reject(new Error("unreachable")) });
    expect(await screen.findByRole("alert")).toHaveTextContent(/unreachable/);
  });

  it("offers the person's record with nothing ticked, and sends only what they tick", async () => {
    const keepResearcher = vi.fn(() => Promise.resolve(KEPT));
    const members = vi.fn().mockResolvedValueOnce(OWNED).mockResolvedValue(KEPT_BY_ME);
    const { container } = renderPanel({ members }, vi.fn(), { keepResearcher });
    const user = userEvent.setup();

    await user.click(
      await screen.findByRole("button", {
        name: /Bring in facts from your ORCID record/,
      }),
    );
    const form = await screen.findByRole("form", {
      name: "Choose what to keep",
    });
    const boxes = within(form).getAllByRole("checkbox");
    expect(boxes.length).toBeGreaterThan(0);
    expect(boxes.every((box) => !(box as HTMLInputElement).checked)).toBe(true);
    expect(form).not.toHaveTextContent("@");
    expect(await axe(container)).toHaveNoViolations();

    await user.click(within(form).getByRole("checkbox", { name: /^Keywords:/ }));
    const employment = OFFERED.affiliations?.[0];
    const affiliations = within(form).getByRole("group", {
      name: "Affiliations",
    });
    await user.click(within(affiliations).getAllByRole("checkbox")[0] as HTMLElement);
    await user.click(within(form).getByRole("button", { name: "Keep the ticked facts" }));

    expect(keepResearcher).toHaveBeenCalledWith(PROJECT, {
      sections: ["keywords"],
      affiliations: [employment?.put_code],
      works: [],
      fundings: [],
    });
    expect(await screen.findByRole("status")).toHaveTextContent("Kept.");
    // The people are read again, and the facts kept show on the person's own entry.
    expect(await screen.findByRole("button", { name: /Change what you keep/ })).toBeVisible();
    expect(members).toHaveBeenCalledTimes(2);
  });

  it("ticks all of a section at once", async () => {
    renderPanel({});
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: /Bring in facts/ }));
    const works = await screen.findByRole("group", { name: "Works" });
    await user.click(within(works).getByRole("button", { name: /Tick all/ }));
    expect(
      within(works)
        .getAllByRole("checkbox")
        .every((box) => (box as HTMLInputElement).checked),
    ).toBe(true);
  });

  it("lets the person withdraw only what they kept", async () => {
    const withdrawResearcher = vi.fn(() => Promise.resolve([]));
    const someone = { ...KEPT[0], orcid_id: COLLEAGUE } as ResearcherRecord;
    const both: ProjectMembers = {
      ...KEPT_BY_ME,
      members: KEPT_BY_ME.members.map((m) => (m.is_you ? m : { ...m, record: someone })),
    };
    renderPanel({ members: () => Promise.resolve(both) }, vi.fn(), {
      withdrawResearcher,
    });
    const user = userEvent.setup();
    const withdraw = await screen.findAllByRole("button", {
      name: "Withdraw what you kept",
    });
    expect(withdraw).toHaveLength(1);
    expect(
      within(entries()[0] as HTMLElement).getByRole("button", {
        name: "Withdraw what you kept",
      }),
    ).toBeVisible();
    await user.click(withdraw[0] as HTMLElement);
    expect(withdrawResearcher).toHaveBeenCalledWith(PROJECT);
    expect(await screen.findByRole("status")).toHaveTextContent("no longer given");
  });

  it("lists the facts of people who are no longer members", async () => {
    const gone = {
      ...KEPT[0],
      orcid_id: "https://orcid.org/0000-0001-5000-0007",
    } as ResearcherRecord;
    renderPanel({
      members: () => Promise.resolve({ ...OWNED, former_researchers: [gone] }),
    });
    const heading = await screen.findByRole("heading", {
      name: "No longer members",
    });
    expect(heading).toBeVisible();
    expect(screen.getAllByRole("link", { name: /0000-0001-5000-0007/ }).length).toBeGreaterThan(0);
  });

  it("says when the ORCID record cannot be read", async () => {
    renderPanel({}, vi.fn(), {
      orcidRecord: () => Promise.reject(new Error("ORCID could not be reached")),
    });
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: /Bring in facts/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent("ORCID could not be reached");
  });
});
