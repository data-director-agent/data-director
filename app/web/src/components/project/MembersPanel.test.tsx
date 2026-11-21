import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";

import lastOwnerFixture from "../../../fixtures/project-members-last-owner.json";
import membersFixture from "../../../fixtures/project-members.json";
import { ActiveProjectTestContext } from "../../project/active";
import {
  type MembersApi,
  MembersApiContext,
  MembersRefused,
  type ProjectMembers,
} from "../../project/members";
import type { Problem } from "../../run/types";
import { MembersPanel } from "./MembersPanel";

// What the server says (app/tests/test_project_members.py): an owner, and the colleague they added.
const OWNED = membersFixture as ProjectMembers;
const LAST_OWNER = lastOwnerFixture as Problem;
const PROJECT = "01900000-0000-7000-8000-000000000001";
const COLLEAGUE = "https://orcid.org/0000-0002-1694-233X";
const ME = "https://orcid.org/0000-0002-1825-0097";

/** The same project as its plain member sees it: no managing, and leaving allowed. */
const JOINED: ProjectMembers = {
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

function renderPanel(api: Partial<MembersApi>, reloadProjects = vi.fn()) {
  const full: MembersApi = {
    members: () => Promise.resolve(OWNED),
    addMember: () => Promise.resolve(OWNED),
    changeRole: () => Promise.resolve(OWNED),
    removeMember: () => Promise.resolve(OWNED),
    ...api,
  };
  return render(
    <ActiveProjectTestContext.Provider
      value={{ projectId: PROJECT, projects: [], setProjectId: vi.fn(), reloadProjects }}
    >
      <MembersApiContext.Provider value={full}>
        <MembersPanel projectId={PROJECT} />
      </MembersApiContext.Provider>
    </ActiveProjectTestContext.Provider>,
  );
}

describe("MembersPanel", () => {
  it("shows an owner each member by ORCID iD, and the controls the server offers", async () => {
    const { container } = renderPanel({});
    const list = await screen.findByRole("list");
    const entries = within(list).getAllByRole("listitem");
    expect(entries).toHaveLength(2);
    expect(entries[0]).toHaveTextContent("(you)");
    expect(within(entries[0] as HTMLElement).getByRole("link")).toHaveAttribute("href", ME);
    // The last owner is neither demoted nor removed; the colleague may be both.
    expect(within(entries[0] as HTMLElement).queryByRole("button")).toBeNull();
    expect(within(entries[1] as HTMLElement).getByRole("button", { name: /Make owner/ })).toBeVisible();
    expect(within(entries[1] as HTMLElement).getByRole("button", { name: /Remove/ })).toBeVisible();
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
    const field = await screen.findByRole("textbox", { name: "Their ORCID iD" });
    await user.type(field, "0000-0002-1694-233X");
    await user.click(screen.getByRole("radio", { name: /^Owner/ }));
    await user.click(screen.getByRole("button", { name: "Add to the project" }));
    expect(addMember).toHaveBeenCalledWith(PROJECT, "0000-0002-1694-233X", "owner");
    expect(await screen.findByRole("status")).toHaveTextContent(/Added 0000-0002-1694-233X/);
    expect(field).toHaveValue("");
  });

  it("keeps what was typed when the server refuses it", async () => {
    const addMember = vi.fn(() => Promise.reject(new MembersRefused({ ...LAST_OWNER, type: "already-member", detail: "already a member" })));
    renderPanel({ addMember });
    const user = userEvent.setup();
    const field = await screen.findByRole("textbox", { name: "Their ORCID iD" });
    await user.type(field, ME);
    await user.click(screen.getByRole("button", { name: "Add to the project" }));
    expect(await screen.findByRole("status")).toHaveTextContent(/already a member/);
    expect(field).toHaveValue(ME);
  });

  it("asks before removing a member", async () => {
    const removeMember = vi.fn(() =>
      Promise.resolve({ ...OWNED, members: OWNED.members.slice(0, 1) }),
    );
    renderPanel({ removeMember });
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: /Remove/ }));
    const dialog = await screen.findByRole("dialog", { name: "Remove a member" });
    expect(removeMember).not.toHaveBeenCalled();
    await user.click(within(dialog).getByRole("button", { name: "Remove" }));
    expect(removeMember).toHaveBeenCalledWith(PROJECT, COLLEAGUE);
    expect(await screen.findByRole("status")).toHaveTextContent(/no longer a member/);
    expect(screen.getAllByRole("listitem")).toHaveLength(1);
  });

  it("leaves after asking, and goes back to the projects", async () => {
    const removeMember = vi.fn(() => Promise.resolve(null));
    const reloadProjects = vi.fn();
    renderPanel({ members: () => Promise.resolve(JOINED), removeMember }, reloadProjects);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Leave this project" }));
    const dialog = await screen.findByRole("dialog", { name: "Leave this project" });
    await user.click(within(dialog).getByRole("button", { name: "Leave" }));
    expect(removeMember).toHaveBeenCalledWith(PROJECT, COLLEAGUE);
    await vi.waitFor(() => expect(reloadProjects).toHaveBeenCalled());
    expect(window.location.pathname).toBe("/projects");
  });

  it("says when the members cannot be read", async () => {
    renderPanel({ members: () => Promise.reject(new Error("unreachable")) });
    expect(await screen.findByRole("alert")).toHaveTextContent(/unreachable/);
  });
});
