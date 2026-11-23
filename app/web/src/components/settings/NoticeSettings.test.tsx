import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";

import { NOTICE_KINDS, useNoticeChoices } from "../../session/notices";
import { NoticeSettings } from "./NoticeSettings";

afterEach(() => localStorage.clear());

function Hidden() {
  const { hidden } = useNoticeChoices();
  return <output aria-label="hidden">{[...hidden].join(",")}</output>;
}

describe("NoticeSettings", () => {
  it("shows every kind of update by default, and remembers one turned off", async () => {
    const { container } = render(
      <>
        <NoticeSettings teams={[]} />
        <Hidden />
      </>,
    );
    const boxes = screen.getAllByRole("checkbox");
    expect(boxes).toHaveLength(NOTICE_KINDS.length);
    for (const box of boxes) expect(box).toBeChecked();
    const [first] = boxes;
    const [kind] = NOTICE_KINDS;
    if (!first || !kind) throw new Error("no kinds of update");
    await userEvent.click(first);
    expect(first).not.toBeChecked();
    expect(screen.getByLabelText("hidden")).toHaveTextContent(kind.kind);
    expect(await axe(container)).toHaveNoViolations();
  });

  it("shows a steward where their team is emailed", () => {
    render(
      <NoticeSettings
        teams={[
          { teamId: "library-rdm", name: "Library", notify: "rdm@example.ac.uk", notifyOn: ["opened"] },
          { teamId: "faculty", name: "Faculty", notifyOn: [] },
        ]}
      />,
    );
    expect(screen.getByText("rdm@example.ac.uk")).toBeInTheDocument();
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
  });
});
