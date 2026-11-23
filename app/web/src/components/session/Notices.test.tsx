import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";

import fixture from "../../../fixtures/notices.json";
import type { Notice } from "../../session/notices";
import { setShown } from "../../session/notices";
import { NoticesMenu } from "./Notices";
import { AnnouncerProvider } from "../ui/Announcer";

const notices = fixture.notices as Notice[];

function show(found: Notice[] = notices) {
  return render(
    <AnnouncerProvider>
      <NoticesMenu load={() => Promise.resolve(found)} />
    </AnnouncerProvider>,
  );
}

afterEach(() => localStorage.clear());

describe("NoticesMenu", () => {
  it("counts the updates not seen, and opening the list marks them seen", async () => {
    const { container } = show();
    const summary = await screen.findByText("Updates");
    await waitFor(() => expect(summary).toHaveTextContent("1 new"));
    await userEvent.click(summary);
    const link = screen.getByRole("link", { name: notices[0]?.subject ?? "" });
    expect(link).toHaveAttribute("href", notices[0]?.path);
    expect(summary).not.toHaveTextContent("new");
    expect(await axe(container)).toHaveNoViolations();
  });

  it("leaves out the kinds the person chose not to be shown", async () => {
    setShown("waiting", false);
    show();
    await userEvent.click(await screen.findByText("Updates"));
    expect(screen.queryByRole("link", { name: notices[0]?.subject ?? "" })).not.toBeInTheDocument();
    expect(screen.getByText(/Nothing from a data steward/)).toBeInTheDocument();
  });
});
