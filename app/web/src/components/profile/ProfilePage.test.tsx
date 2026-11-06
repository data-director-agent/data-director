import { render, screen } from "@testing-library/react";
import { axe } from "jest-axe";

import { DEVELOPMENT, signedIn } from "../../test/session";
import { ProfilePage } from "./ProfilePage";

describe("ProfilePage", () => {
  it("shows the name, the iD as a link and how the person is known", () => {
    render(<ProfilePage session={signedIn()} />);
    expect(screen.getByRole("heading", { name: "Your profile" })).toBeVisible();
    expect(screen.getByText("Josiah Carberry")).toBeVisible();
    expect(screen.getByRole("link", { name: /0000-0002-1825-0097/ })).toHaveAttribute(
      "href",
      "https://sandbox.orcid.org/0000-0002-1825-0097",
    );
    expect(screen.getByText("authenticated by sandbox.orcid.org")).toBeVisible();
    expect(screen.getByText(/keeps no email address/)).toBeVisible();
  });

  it("says when the session ends", () => {
    const { container } = render(<ProfilePage session={signedIn("2030-01-01T12:00:00Z")} />);
    expect(container.querySelector("time")).toHaveAttribute("datetime", "2030-01-01T12:00:00.000Z");
  });

  it("says that a development server signs nobody in", () => {
    render(<ProfilePage session={DEVELOPMENT} />);
    expect(screen.getByText(/does not sign anyone in/)).toBeVisible();
    expect(screen.queryByText("Session ends")).toBeNull();
  });

  it("has no accessibility violations", async () => {
    const { container } = render(<ProfilePage session={signedIn()} />);
    expect(await axe(container)).toHaveNoViolations();
  });
});
