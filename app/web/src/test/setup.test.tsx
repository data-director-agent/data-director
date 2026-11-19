import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { useState } from "react";

import { Button } from "../components/ui/Button";

// A pending button that has focus announces its label through React Aria's live announcer, which
// keeps the entry in `document.body` after the test. The shared setup empties it, so a later
// test that checks the whole body with axe finds nothing left behind.

function Pending() {
  const [busy, setBusy] = useState(false);
  return (
    <Button isPending={busy} onPress={() => setBusy(true)}>
      Go
    </Button>
  );
}

describe("the shared test setup", () => {
  it("lets a pending button announce itself", async () => {
    const user = userEvent.setup();
    render(<Pending />);
    await user.click(screen.getByRole("button", { name: "Go" }));
    expect(screen.getByRole("button", { name: "Go" })).toHaveAttribute("aria-disabled", "true");
  });

  it("leaves no announcement behind for the next test", async () => {
    expect(await axe(document.body)).toHaveNoViolations();
  });
});
