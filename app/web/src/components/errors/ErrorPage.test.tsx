import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";

import { App } from "../../App";
import reference from "../../../fixtures/agents.json";
import { normalise } from "../../manifest/normalise";
import type { RawAgentsResponse } from "../../manifest/types";
import { DEVELOPMENT, WithSession, fakeSessionApi } from "../../test/session";
import { ErrorBoundary } from "./ErrorBoundary";
import { NotFoundPage } from "./ErrorPage";

const directory = normalise(reference as unknown as RawAgentsResponse);

function Broken(): never {
  throw new Error("boom");
}

describe("the not-found page", () => {
  it("names the missing address and offers a way back", async () => {
    const { container } = render(<NotFoundPage path="/no/such/page" />);
    expect(screen.getByRole("heading", { level: 1, name: "Page not found" })).toBeInTheDocument();
    expect(screen.getByText("/no/such/page")).toBeVisible();
    expect(screen.getByRole("link", { name: /Go to the conversation/ })).toHaveAttribute("href", "/");
    expect(await axe(container)).toHaveNoViolations();
  });

  it("is what the app shows at an address it has no page for", async () => {
    history.pushState(null, "", "/no/such/page");
    render(
      <WithSession api={fakeSessionApi(DEVELOPMENT)}>
        <App load={() => Promise.resolve(directory)} />
      </WithSession>,
    );
    expect(await screen.findByRole("heading", { level: 1, name: "Page not found" })).toBeInTheDocument();
    expect(document.title).toBe("Page not found · Data Director");
  });
});

describe("the error boundary", () => {
  beforeEach(() => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
  });

  it("shows the something-went-wrong page instead of a blank window, and says so as an alert", async () => {
    render(
      <ErrorBoundary resetKey="/">
        <Broken />
      </ErrorBoundary>,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("Something went wrong");
    expect(screen.queryByText("boom")).toBeNull();
  });

  it("tries the page again when asked", async () => {
    let fail = true;
    function Sometimes() {
      if (fail) throw new Error("boom");
      return <p>Recovered</p>;
    }
    render(
      <ErrorBoundary resetKey="/">
        <Sometimes />
      </ErrorBoundary>,
    );
    fail = false;
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(screen.getByText("Recovered")).toBeVisible();
  });
});
